"""
Checkpoint System for Multi-Agent Backtracking

Provides:
- TerminalCheckpoint: Records terminal commands with undo support
- WebCheckpoint: Records web tool calls with retry support
- CheckpointManager: Manages per-task checkpoint stacks

Usage:
    mgr = CheckpointManager()
    
    # Terminal: record command, get undo capability
    cp = mgr.record_terminal(task_id, command, cwd_before, cwd_after, session_id, result)
    
    # Later, undo last reversible command
    undo_cp = mgr.pop_undo(task_id)
    if undo_cp:
        execute(undo_cp.undo_command)
    
    # Web: record with auto-retry
    cp = mgr.record_web(task_id, tool_name, tool_args, result)
    while mgr.should_retry(cp):
        mgr.increment_retry(cp)
        result = retry_tool_call(...)
        cp.result = result
    
    # Clear on task completion
    mgr.clear_task(task_id)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import uuid
import re
import logging
import os
import json
import shutil

logger = logging.getLogger("checkpoint")


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TerminalCheckpoint:
    """
    Checkpoint for a terminal command with undo support.
    
    Attributes:
        id: Unique checkpoint identifier
        timestamp: When the command was executed
        command: The shell command that was run
        cwd_before: Working directory before execution
        cwd_after: Working directory after execution
        session_id: Shell session ID
        result: Result dict from run_command
        undo_command: Command to reverse this action (None if not reversible)
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    command: str = ""
    cwd_before: str = ""
    cwd_after: str = ""
    session_id: str = ""
    result: Dict[str, Any] = field(default_factory=dict)
    undo_command: Optional[str] = None

    # Deletion/back-up metadata (Phase 1 – not yet wired into run_command/undo)
    #
    # When we later support reversible deletions, these fields will hold:
    # - backup_path: directory where backups for this checkpoint are stored
    # - deleted_items: list of deleted filesystem objects with metadata
    # - is_deletion: flag indicating this command deleted something
    backup_path: Optional[str] = None
    deleted_items: List[Dict[str, Any]] = field(default_factory=list)
    is_deletion: bool = False

    @property
    def reversible(self) -> bool:
        """Returns True if this command can be undone"""
        return self.undo_command is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "command": self.command,
            "cwd_before": self.cwd_before,
            "cwd_after": self.cwd_after,
            "session_id": self.session_id,
            "result": self.result,
            "undo_command": self.undo_command,
            "reversible": self.reversible,
            "backup_path": self.backup_path,
            "deleted_items": self.deleted_items,
            "is_deletion": self.is_deletion,
        }


@dataclass
class WebCheckpoint:
    """
    Checkpoint for a web tool call with retry support.
    
    Attributes:
        id: Unique checkpoint identifier
        timestamp: When the tool was called
        tool_name: Name of the MCP tool (search_web, scrape_url, etc.)
        tool_args: Arguments passed to the tool
        result: Result dict from the tool
        retry_count: Number of retry attempts made
        max_retries: Maximum retries allowed
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3

    @property
    def success(self) -> bool:
        """Returns True if the tool call succeeded"""
        return self.result.get("ok", False)

    @property
    def can_retry(self) -> bool:
        """Returns True if more retries are available"""
        return not self.success and self.retry_count < self.max_retries

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "result": self.result,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "success": self.success,
        }


# ============================================================================
# Deletion Detection & Backup (Phase 1 infrastructure)
# ============================================================================


class DeletionDetector:
    """
    Detects deletion-style shell commands and extracts their targets.

    This is *syntax-level* detection only. It does not touch the filesystem.

    Supported patterns (initial set):
    - rm <path>...
    - rm -r|-rf|-f <path>...
    - rmdir <path>...

    Returned format (per item):
        {
            "original_arg": "<as in command>",
            "path": "/abs/path",
            "is_dir": bool,
        }
    """

    _RM_RE = re.compile(r"^rm\s+(.+)$")
    _RMDIR_RE = re.compile(r"^rmdir\s+(.+)$")

    def _split_args(self, arg_str: str) -> List[str]:
        """
        Very small arg splitter. We keep this conservative (no full shell parsing).
        """
        return [p for p in arg_str.strip().split() if p]

    def _normalize_path(self, raw: str, cwd_before: str) -> str:
        """
        Convert a raw path argument to an absolute normalized path.
        """
        # Expand user (~) and env vars
        expanded = os.path.expanduser(os.path.expandvars(raw))
        p = Path(expanded)
        if not p.is_absolute():
            p = Path(cwd_before) / p
        return str(p.resolve())

    def detect(self, command: str, cwd_before: str) -> List[Dict[str, Any]]:
        """
        Detect deletion targets for a command.

        Returns a list of target dicts. Empty list means "not a deletion"
        (or nothing we can confidently reason about).
        """
        cmd = command.strip()
        targets: List[Dict[str, Any]] = []

        # rm ...
        m = self._RM_RE.match(cmd)
        if m:
            raw_args = self._split_args(m.group(1))
            # Strip leading flags (-r, -rf, -f, etc.)
            path_args = [a for a in raw_args if not a.startswith("-")]
            for arg in path_args:
                abs_path = self._normalize_path(arg, cwd_before)
                targets.append(
                    {
                        "original_arg": arg,
                        "path": abs_path,
                        # We don't hit the filesystem here; caller can refine
                        "is_dir": abs_path.endswith(os.sep),
                    }
                )
            return targets

        # rmdir ...
        m = self._RMDIR_RE.match(cmd)
        if m:
            raw_args = self._split_args(m.group(1))
            for arg in raw_args:
                abs_path = self._normalize_path(arg, cwd_before)
                targets.append(
                    {
                        "original_arg": arg,
                        "path": abs_path,
                        "is_dir": True,
                    }
                )
            return targets

        return targets


class BackupManager:
    """
    Manages filesystem backups for potentially destructive terminal commands.

    Phase 1: defines structure and helpers, *without* being wired into
    run_command/undo yet.

    Backup layout (per task/checkpoint):
        base_dir/
          {task_id}/
            {checkpoint_id}/
              metadata.json
              data/
                item_00001
                item_00002

    The actual content format (file vs directory tarball, etc.) is left flexible
    for later phases.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(
            base_dir or os.path.join(os.path.expanduser("~"), ".checkpoint_backups")
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"BackupManager initialized at {self.base_dir}")

    # ----- Path helpers -----------------------------------------------------

    def task_checkpoint_dir(self, task_id: str, checkpoint_id: str) -> Path:
        """
        Directory that will hold backups for a specific checkpoint.
        """
        return self.base_dir / task_id / checkpoint_id

    def metadata_path(self, task_id: str, checkpoint_id: str) -> Path:
        return self.task_checkpoint_dir(task_id, checkpoint_id) / "metadata.json"

    def data_dir(self, task_id: str, checkpoint_id: str) -> Path:
        return self.task_checkpoint_dir(task_id, checkpoint_id) / "data"

    # ----- Planning (no/limited I/O) ----------------------------------------

    def plan_backup_layout(
        self,
        task_id: str,
        checkpoint_id: str,
        deleted_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute where backups *would* be stored for a given deletion checkpoint.

        This is a pure helper that does not touch the filesystem directly
        (aside from ensuring parent dirs exist).
        """
        cp_dir = self.task_checkpoint_dir(task_id, checkpoint_id)
        data_dir = self.data_dir(task_id, checkpoint_id)
        cp_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

        layout: Dict[str, Any] = {
            "checkpoint_dir": str(cp_dir),
            "data_dir": str(data_dir),
            "items": [],
        }

        for idx, item in enumerate(deleted_items, start=1):
            item_id = f"item_{idx:05d}"
            layout["items"].append(
                {
                    "item_id": item_id,
                    "original_path": item.get("path"),
                    "original_arg": item.get("original_arg"),
                    "is_dir": bool(item.get("is_dir")),
                    "backup_path": str(data_dir / item_id),
                }
            )

        return layout

    def write_metadata(
        self,
        task_id: str,
        checkpoint_id: str,
        meta: Dict[str, Any],
    ) -> None:
        """
        Persist backup metadata to disk for later inspection/restore.
        """
        meta_path = self.metadata_path(task_id, checkpoint_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    # ----- Backup & Restore (Phase 3) ---------------------------------------

    def backup_deleted_items(
        self,
        task_id: str,
        checkpoint_id: str,
        deleted_items: List[Dict[str, Any]],
        *,
        command: str,
        cwd_before: str,
    ) -> str:
        """
        Create on-disk backups for deleted items and persist metadata.

        Returns:
            The checkpoint backup directory path (string).
        """
        layout = self.plan_backup_layout(
            task_id=task_id,
            checkpoint_id=checkpoint_id,
            deleted_items=deleted_items,
        )

        # Copy content
        for item_layout in layout["items"]:
            src = Path(item_layout["original_path"])
            dst = Path(item_layout["backup_path"])

            if not src.exists():
                # Nothing to back up (already gone)
                continue

            if item_layout["is_dir"]:
                # Ensure parent exists and copy directory tree
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        meta = {
            "task_id": task_id,
            "backup_id": checkpoint_id,
            "command": command,
            "cwd_before": cwd_before,
            "deleted_items": deleted_items,
            "layout": layout,
        }
        self.write_metadata(task_id, checkpoint_id, meta)
        return layout["checkpoint_dir"]

    def restore_from_checkpoint_dir(self, checkpoint_dir: str) -> Dict[str, Any]:
        """
        Restore files/directories from a backup checkpoint directory.

        Args:
            checkpoint_dir: Path returned by backup_deleted_items / plan_backup_layout

        Returns:
            Dict with {ok, restored_count, errors}
        """
        cp_path = Path(checkpoint_dir)
        meta_path = cp_path / "metadata.json"

        if not meta_path.exists():
            return {
                "ok": False,
                "restored_count": 0,
                "errors": [f"metadata.json not found in {checkpoint_dir}"],
            }

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        layout = meta.get("layout") or {}
        items = layout.get("items") or []

        restored = 0
        errors: List[str] = []

        for item in items:
            src = Path(item.get("backup_path", ""))
            dst = Path(item.get("original_path", ""))
            is_dir = bool(item.get("is_dir"))

            if not src.exists():
                errors.append(f"backup missing for {dst}")
                continue

            try:
                if is_dir:
                    # Remove existing destination (if any) then restore
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                restored += 1
            except Exception as e:
                errors.append(f"failed to restore {dst}: {e}")

        return {
            "ok": len(errors) == 0,
            "restored_count": restored,
            "errors": errors,
        }


# ============================================================================
# Undo Command Generator
# ============================================================================


class UndoGenerator:
    """
    Generates undo commands for reversible *non-destructive* shell operations.

    NOTE: Destructive operations (rm, mv, cp, chmod, chown, etc.) remain
    non-reversible at the command level. Deletion undo will instead be
    implemented via backups handled by BackupManager, not by synthesizing
    shell commands here.
    """

    def generate(self, command: str, cwd_before: str) -> Optional[str]:
        """
        Generate an undo command for the given shell command.

        Args:
            command: The shell command that was executed
            cwd_before: The working directory before execution

        Returns:
            The undo command string, or None if not reversible
        """
        cmd = command.strip()

        # mkdir [-p] <path>
        m = re.match(r"^mkdir\s+(?:-p\s+)?(.+)$", cmd)
        if m:
            path = m.group(1).strip()
            # Handle multiple paths
            paths = path.split()
            if len(paths) == 1:
                return f"rmdir {path}"
            else:
                # Multiple directories - rmdir in reverse order
                return "rmdir " + " ".join(reversed(paths))

        # touch <path> (creates new file)
        m = re.match(r"^touch\s+(.+)$", cmd)
        if m:
            path = m.group(1).strip()
            return f"rm {path}"

        # cd <path>
        m = re.match(r"^cd\s+", cmd)
        if m:
            return f"cd {cwd_before}"

        # echo ... > file (redirect to new file)
        m = re.match(r"^echo\s+.*>\s*([^\s]+)$", cmd)
        if m:
            path = m.group(1).strip()
            return f"rm {path}"

        # echo ... >> file (append - not reversible cleanly)
        if re.match(r"^echo\s+.*>>", cmd):
            return None

        # cat > file (heredoc style)
        m = re.match(r"^cat\s*>\s*([^\s]+)", cmd)
        if m:
            path = m.group(1).strip()
            return f"rm {path}"

        # printf ... > file
        m = re.match(r"^printf\s+.*>\s*([^\s]+)$", cmd)
        if m:
            path = m.group(1).strip()
            return f"rm {path}"

        # Not reversible (rm, mv, cp, chmod, chown, etc.)
        # These require approval and are intentionally not undoable here.
        return None


# ============================================================================
# Checkpoint Manager
# ============================================================================

class CheckpointManager:
    """
    Manages per-task checkpoint stacks for terminal undo and web retry.
    
    Terminal operations are stored in a stack (LIFO) for undo.
    Web operations track retry counts for automatic retry.
    
    Checkpoints are cleared when a task completes.
    """

    def __init__(self, default_max_retries: int = 3):
        """
        Initialize the checkpoint manager.
        
        Args:
            default_max_retries: Default max retry attempts for web tools
        """
        self._terminal_stacks: Dict[str, List[TerminalCheckpoint]] = {}
        self._web_stacks: Dict[str, List[WebCheckpoint]] = {}
        self._undo_gen = UndoGenerator()
        self.default_max_retries = default_max_retries
        logger.info("CheckpointManager initialized")

    # -------------------------------------------------------------------------
    # Terminal Operations
    # -------------------------------------------------------------------------

    def record_terminal(
        self,
        task_id: str,
        command: str,
        cwd_before: str,
        cwd_after: str,
        session_id: str,
        result: Dict[str, Any],
        *,
        backup_path: Optional[str] = None,
        deleted_items: Optional[List[Dict[str, Any]]] = None,
        is_deletion: bool = False,
    ) -> TerminalCheckpoint:
        """
        Record a terminal command execution.
        
        Args:
            task_id: Unique task identifier
            command: The shell command that was executed
            cwd_before: Working directory before execution
            cwd_after: Working directory after execution
            session_id: Shell session ID
            result: Result dict from run_command
            
        Returns:
            The created TerminalCheckpoint
        """
        undo_cmd = self._undo_gen.generate(command, cwd_before)
        
        cp = TerminalCheckpoint(
            command=command,
            cwd_before=cwd_before,
            cwd_after=cwd_after,
            session_id=session_id,
            result=result,
            undo_command=undo_cmd,
            backup_path=backup_path,
            deleted_items=deleted_items or [],
            is_deletion=is_deletion,
        )
        
        if task_id not in self._terminal_stacks:
            self._terminal_stacks[task_id] = []
        self._terminal_stacks[task_id].append(cp)
        
        logger.info(
            f"[{task_id}] Recorded terminal checkpoint: {command[:50]}... "
            f"(reversible={cp.reversible})"
        )
        
        return cp

    def pop_undo(self, task_id: str) -> Optional[TerminalCheckpoint]:
        """
        Pop and return the last undoable checkpoint for this task.
        
        A checkpoint is considered undoable if:
        - It has an undo_command (non-destructive reversible operation), OR
        - It is marked as a deletion (is_deletion=True) with backup metadata.
        
        Other checkpoints are skipped (removed from stack).
        
        Args:
            task_id: The task to undo from
            
        Returns:
            The checkpoint to undo/restore, or None if nothing to undo
        """
        stack = self._terminal_stacks.get(task_id, [])
        
        while stack:
            cp = stack.pop()
            if cp.undo_command or (cp.is_deletion and cp.backup_path):
                logger.info(
                    f"[{task_id}] Popped undo checkpoint: {cp.command[:50]}... "
                    f"(undo_command={cp.undo_command}, is_deletion={cp.is_deletion})"
                )
                return cp
            logger.debug(
                f"[{task_id}] Skipped non-undoable: {cp.command[:50]}..."
            )
        
        logger.info(f"[{task_id}] Nothing to undo")
        return None

    def peek_undo(self, task_id: str) -> Optional[TerminalCheckpoint]:
        """
        Peek at the last reversible checkpoint without removing it.
        
        Args:
            task_id: The task to peek
            
        Returns:
            The last reversible checkpoint, or None
        """
        stack = self._terminal_stacks.get(task_id, [])
        
        for cp in reversed(stack):
            if cp.undo_command:
                return cp
        
        return None

    def get_terminal_stack(self, task_id: str) -> List[TerminalCheckpoint]:
        """
        Get all terminal checkpoints for a task (for inspection).
        
        Returns a copy of the stack.
        """
        return self._terminal_stacks.get(task_id, []).copy()

    def get_undo_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get a summary of all reversible commands for this task.
        
        Returns a list of dicts with command and undo_command.
        """
        stack = self._terminal_stacks.get(task_id, [])
        return [
            {"command": cp.command, "undo_command": cp.undo_command}
            for cp in stack
            if cp.undo_command
        ]

    # -------------------------------------------------------------------------
    # Web Operations
    # -------------------------------------------------------------------------

    def record_web(
        self,
        task_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Dict[str, Any],
        max_retries: Optional[int] = None,
    ) -> WebCheckpoint:
        """
        Record a web tool call.
        
        Args:
            task_id: Unique task identifier
            tool_name: Name of the MCP tool
            tool_args: Arguments passed to the tool
            result: Result dict from the tool
            max_retries: Override default max retries
            
        Returns:
            The created WebCheckpoint
        """
        cp = WebCheckpoint(
            tool_name=tool_name,
            tool_args=tool_args,
            result=result,
            max_retries=max_retries if max_retries is not None else self.default_max_retries,
        )
        
        if task_id not in self._web_stacks:
            self._web_stacks[task_id] = []
        self._web_stacks[task_id].append(cp)
        
        logger.info(
            f"[{task_id}] Recorded web checkpoint: {tool_name} "
            f"(success={cp.success})"
        )
        
        return cp

    def should_retry(self, checkpoint: WebCheckpoint) -> bool:
        """
        Check if a failed web checkpoint should be retried.
        
        Returns True if the call failed and retries remain.
        """
        return checkpoint.can_retry

    def increment_retry(self, checkpoint: WebCheckpoint) -> int:
        """
        Increment the retry count for a checkpoint.
        
        Returns the new retry count.
        """
        checkpoint.retry_count += 1
        logger.info(
            f"Retry {checkpoint.retry_count}/{checkpoint.max_retries} "
            f"for {checkpoint.tool_name}"
        )
        return checkpoint.retry_count

    def update_result(self, checkpoint: WebCheckpoint, result: Dict[str, Any]):
        """
        Update the result of a checkpoint (after retry).
        """
        checkpoint.result = result
        checkpoint.timestamp = datetime.now()

    def get_web_stack(self, task_id: str) -> List[WebCheckpoint]:
        """
        Get all web checkpoints for a task.
        
        Returns a copy of the stack.
        """
        return self._web_stacks.get(task_id, []).copy()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def clear_task(self, task_id: str):
        """
        Clear all checkpoints for a completed task.
        
        Should be called when a task finishes (success or failure).
        """
        terminal_count = len(self._terminal_stacks.pop(task_id, []))
        web_count = len(self._web_stacks.pop(task_id, []))
        logger.info(
            f"[{task_id}] Cleared checkpoints: "
            f"{terminal_count} terminal, {web_count} web"
        )

    def clear_all(self):
        """Clear all checkpoints for all tasks."""
        self._terminal_stacks.clear()
        self._web_stacks.clear()
        logger.info("Cleared all checkpoints")

    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        """
        Get a summary of checkpoints for a task.
        
        Useful for debugging and inspection.
        """
        terminal_stack = self._terminal_stacks.get(task_id, [])
        web_stack = self._web_stacks.get(task_id, [])
        
        return {
            "task_id": task_id,
            "terminal_count": len(terminal_stack),
            "terminal_reversible": sum(1 for cp in terminal_stack if cp.reversible),
            "web_count": len(web_stack),
            "web_failed": sum(1 for cp in web_stack if not cp.success),
            "terminal_checkpoints": [cp.to_dict() for cp in terminal_stack],
            "web_checkpoints": [cp.to_dict() for cp in web_stack],
        }


# ============================================================================
# Global Instance (optional convenience)
# ============================================================================

# Shared instance for use across the application
_global_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    """
    Get the global CheckpointManager instance.
    
    Creates one if it doesn't exist.
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = CheckpointManager()
    return _global_manager


def reset_checkpoint_manager():
    """Reset the global checkpoint manager (mainly for testing)."""
    global _global_manager
    if _global_manager:
        _global_manager.clear_all()
    _global_manager = None

