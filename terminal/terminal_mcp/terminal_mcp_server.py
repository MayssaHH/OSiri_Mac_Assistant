import os
import sys
import subprocess
import time
import uuid
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP

# Add parent directories to path for common imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.checkpoint import CheckpointManager

mcp = FastMCP(name="Terminal MCP Server")

# Global checkpoint manager for undo support
checkpoint_manager = CheckpointManager()

# This is a stronger safety layer that rejects commands that are known to be dangerous.
HIGH_PATTERNS = [
    re.compile(r"\brm\b"),
    re.compile(r"\bmv\b"),
    re.compile(r"\bcp\b"),
    re.compile(r"\bchmod\b"),
    re.compile(r"\bchown\b"),
    re.compile(r"\bkill\b"),
    re.compile(r"\bpkill\b"),
    re.compile(r"\bssh\b"),
    re.compile(r"\bscp\b"),
    re.compile(r"\bcurl\b.*\|\s*(sh|bash|zsh)"),  # curl | sh
    re.compile(r"\bwget\b.*\|\s*(sh|bash|zsh)"),
    re.compile(r"\bdd\b"),
    re.compile(r"\bdiskutil\b"),
    re.compile(r"\bmkfs\b"),
]

MEDIUM_PATTERNS = [
    re.compile(r"\bgit\s+clone\b"),
    re.compile(r"\bpip\s+install\b"),
    re.compile(r"\bbrew\s+install\b"),
    re.compile(r"\bnpm\s+install\b"),
    re.compile(r"\byarn\s+add\b"),
    re.compile(r"\bcurl\b"),
    re.compile(r"\bwget\b"),
]

DENY_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*;\s*\}\s*;"),  # fork bomb
]

SANDBOX_ROOT = os.environ.get(
    "TERMINAL_SANDBOX_ROOT",
    ""  # empty means sandbox disabled
)
SANDBOX_ROOT = os.path.expanduser(SANDBOX_ROOT) if SANDBOX_ROOT else ""

def classify_risk(cmd: str) -> str:
    lc = cmd.strip().lower()
    for pat in HIGH_PATTERNS:
        if pat.search(lc):
            return "high"
    for pat in MEDIUM_PATTERNS:
        if pat.search(lc):
            return "medium"
    return "safe"


def _is_denied(cmd: str) -> Optional[str]:
    for pat in DENY_PATTERNS:
        if pat.search(cmd):
            return pat.pattern
    return None


# Here I am defining a dataclass to create shell sessions and store the session information.
@dataclass
class ShellSession:
    proc: subprocess.Popen
    cwd: str
    created_at: float = field(default_factory=time.time)

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, ShellSession] = {}

    def open_shell(self, cwd: Optional[str] = None, shell_path: Optional[str] = None) -> str:
        if cwd is None:
            cwd = os.path.expanduser("~")
        if shell_path is None:
            shell_path = os.environ.get("SHELL", "/bin/zsh")

        proc = subprocess.Popen(
            [shell_path, "-f"],              
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
        )

        session_id = uuid.uuid4().hex
        self.sessions[session_id] = ShellSession(proc=proc, cwd=cwd)
        return session_id

    def close_shell(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if not s:
            return False
        try:
            s.proc.terminate()
        except Exception:
            pass
        self.sessions.pop(session_id, None)
        return True

    def run_command(self, session_id: str, command: str, timeout_s: float = 20.0, approved: bool = False) -> Dict:
        s = self.sessions.get(session_id)
        if not s:
            return {"ok": False, "error": f"Unknown session_id: {session_id}"}

        denied = _is_denied(command)
        if denied:
            return {"ok": False, "error": f"Command blocked by safety policy (pattern: {denied})"}

        risk = classify_risk(command)
        if risk != "safe" and not approved:
            return {
                "ok": False,
                "error": f"Command requires approval (risk={risk})",
                "risk": risk
            }

        done_token = f"__MCP_DONE_{uuid.uuid4().hex}__"
        cwd_token  = f"__MCP_CWD_{uuid.uuid4().hex}__"

        payload = (
            f"{command}\n"
            f"echo {done_token} $?\n"
            f"pwd\n"
            f"echo {cwd_token}\n"
        )
        # Send command
        try:
            s.proc.stdin.write(payload)
            s.proc.stdin.flush()
        except Exception as e:
            return {"ok": False, "error": f"Failed to write to shell: {e}"}

        cmd_out_lines = []
        cwd_lines = []
        start = time.time()
        exit_code = None

        done_re = re.compile(rf"^{re.escape(done_token)}\s+(\d+)\s*$")
        cwd_re  = re.compile(rf"^{re.escape(cwd_token)}\s*$")

        state = "command"

        while time.time() - start < timeout_s:
            line = s.proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue

            line_stripped = line.rstrip("\n")

            if state == "command":
                m = done_re.match(line_stripped)
                if m:
                    exit_code = int(m.group(1))
                    state = "cwd"
                    continue
                cmd_out_lines.append(line_stripped)

            else:  # state == "cwd"
                if cwd_re.match(line_stripped):
                    # last non-empty line before cwd_token is the cwd
                    non_empty = [ln.strip() for ln in cwd_lines if ln.strip()]
                    new_cwd = non_empty[-1] if non_empty else s.cwd
                    s.cwd = new_cwd  # <-- auto-track here

                    if SANDBOX_ROOT and not new_cwd.startswith(SANDBOX_ROOT) and not approved:
                        # close session to avoid running outside sandbox silently
                        self.close_shell(session_id)
                        return {
                            "ok": False,
                            "error": f"Left sandbox root {SANDBOX_ROOT}. Session closed.",
                            "cwd": new_cwd,
                            "risk": risk
                        }
                    return {
                        "ok": True,
                        "exit_code": exit_code if exit_code is not None else -1,
                        "output": "\n".join(cmd_out_lines).strip(),
                        "cwd": new_cwd,
                        "risk": risk
                    }
                cwd_lines.append(line_stripped)

        # timeout
        return {
            "ok": False,
            "error": f"Timeout after {timeout_s}s",
            "partial_output": "\n".join(cmd_out_lines).strip(),
            "partial_cwd_output": "\n".join(cwd_lines).strip(),
            "risk": risk
        }

    def list_shells(self) -> Dict[str, Dict]:
        return {
            sid: {
                "pid": s.proc.pid,
                "cwd": s.cwd,
                "created_at": s.created_at
            }
            for sid, s in self.sessions.items()
        }


manager = SessionManager()

# Here I am defining the MCP tools that will be used to interact with the shell sessions.
@mcp.tool()
def open_shell(cwd: str | None = None) -> dict:
    sid = manager.open_shell(cwd=cwd)
    return {"session_id": sid}

@mcp.tool()
def run_command(
    session_id: str, 
    command: str, 
    timeout_s: float = 20.0, 
    approved: bool = False,
    task_id: str = "",
) -> dict:
    """
    Run a command inside a given shell session.
    
    Args:
        session_id: The shell session to run the command in
        command: The shell command to execute
        timeout_s: Timeout in seconds (default 20)
        approved: Whether risky commands are pre-approved
        task_id: Optional task ID for checkpoint tracking (enables undo)
    
    Returns:
        {ok, output, exit_code, cwd, risk} on success
        {ok, error, ...} on failure
        
    If task_id is provided, the command is recorded in the checkpoint system
    and can be undone with undo_last().
    """
    # Get cwd BEFORE execution
    s = manager.sessions.get(session_id)
    cwd_before = s.cwd if s else ""
    
    # Execute the command
    result = manager.run_command(session_id, command, timeout_s=timeout_s, approved=approved)
    
    # Record checkpoint if task_id provided and command succeeded
    if task_id and result.get("ok", False):
        cwd_after = result.get("cwd", cwd_before)
        cp = checkpoint_manager.record_terminal(
            task_id=task_id,
            command=command,
            cwd_before=cwd_before,
            cwd_after=cwd_after,
            session_id=session_id,
            result=result,
        )
        # Add checkpoint info to result
        result["checkpoint_id"] = cp.id
        result["reversible"] = cp.reversible
        if cp.undo_command:
            result["undo_command"] = cp.undo_command
    
    return result

@mcp.tool()
def close_shell(session_id: str) -> dict:
    ok = manager.close_shell(session_id)
    return {"ok": ok}

@mcp.tool()
def list_shells() -> dict:
    return manager.list_shells()

@mcp.tool()
def get_cwd(session_id: str) -> dict:
    s = manager.sessions.get(session_id)
    if not s:
        return {"ok": False, "error": f"Unknown session_id: {session_id}"}
    return {"ok": True, "cwd": s.cwd}


# ============================================================================
# Checkpoint/Undo Tools
# ============================================================================

@mcp.tool()
def undo_last(task_id: str, session_id: str) -> dict:
    """
    Undo the last reversible command for a task.
    
    Pops the most recent reversible checkpoint and executes its undo command.
    Non-reversible commands (rm, mv, cp, etc.) are skipped.
    
    Args:
        task_id: The task whose last command should be undone
        session_id: The shell session to run the undo command in
        
    Returns:
        {ok, undone_command, undo_command, result} on success
        {ok, error} if nothing to undo
    """
    # Pop the last reversible checkpoint
    cp = checkpoint_manager.pop_undo(task_id)
    
    if not cp:
        return {
            "ok": False, 
            "error": "Nothing to undo - no reversible commands in history"
        }
    
    if not cp.undo_command:
        return {
            "ok": False,
            "error": f"Command '{cp.command}' is not reversible"
        }
    
    # Execute the undo command (with approved=True since this is a controlled undo)
    undo_result = manager.run_command(
        session_id, 
        cp.undo_command, 
        timeout_s=20.0, 
        approved=True
    )
    
    return {
        "ok": undo_result.get("ok", False),
        "undone_command": cp.command,
        "undo_command": cp.undo_command,
        "result": undo_result,
    }


@mcp.tool()
def get_undo_history(task_id: str) -> dict:
    """
    Get the list of reversible commands that can be undone for a task.
    
    Args:
        task_id: The task to get undo history for
        
    Returns:
        {ok, history} where history is a list of {command, undo_command}
    """
    history = checkpoint_manager.get_undo_history(task_id)
    return {
        "ok": True,
        "count": len(history),
        "history": history,
    }


@mcp.tool()
def clear_checkpoints(task_id: str) -> dict:
    """
    Clear all checkpoints for a completed task.
    
    Should be called when a task finishes to free memory.
    
    Args:
        task_id: The task whose checkpoints should be cleared
        
    Returns:
        {ok: True}
    """
    checkpoint_manager.clear_task(task_id)
    return {"ok": True}


def main():
    mcp.run()

if __name__ == "__main__":
    main()
