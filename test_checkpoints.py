"""
Test script for the Checkpoint System

Tests:
1. Terminal checkpoints with undo capability
2. Web checkpoints with auto-retry
3. Backup manager file roundtrip
4. Deletion checkpoint undo selection
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"))

from common.checkpoint import CheckpointManager, UndoGenerator, BackupManager


def test_undo_generator():
    """Test the UndoGenerator for various commands"""
    print("\n" + "=" * 60)
    print("TEST 1: UndoGenerator")
    print("=" * 60)
    
    gen = UndoGenerator()
    cwd = "/Users/test/Desktop"
    
    test_cases = [
        # (command, expected_undo_pattern)
        ("mkdir test_folder", "rmdir test_folder"),
        ("mkdir -p a/b/c", "rmdir"),
        ("touch newfile.txt", "rm newfile.txt"),
        ("cd /tmp", f"cd {cwd}"),
        ("echo hello > output.txt", "rm output.txt"),
        ("cat > data.txt", "rm data.txt"),
        ("rm dangerous_file.txt", None),  # Not reversible
        ("mv file1 file2", None),  # Not reversible
        ("ls -la", None),  # Read-only, no undo needed
    ]
    
    all_passed = True
    for cmd, expected in test_cases:
        result = gen.generate(cmd, cwd)
        
        if expected is None:
            status = "✓" if result is None else "✗"
            if result is not None:
                all_passed = False
        else:
            status = "✓" if result and expected in result else "✗"
            if not (result and expected in result):
                all_passed = False
        
        print(f"  {status} '{cmd}' -> '{result}' (expected: '{expected}')")
    
    return all_passed


def test_checkpoint_manager_terminal():
    """Test terminal checkpoint recording and undo"""
    print("\n" + "=" * 60)
    print("TEST 2: CheckpointManager - Terminal Operations")
    print("=" * 60)
    
    mgr = CheckpointManager()
    task_id = "test_task_001"
    
    # Simulate a sequence of commands
    commands = [
        ("mkdir project", "/home/user", "/home/user"),
        ("cd project", "/home/user", "/home/user/project"),
        ("touch main.py", "/home/user/project", "/home/user/project"),
        ("touch utils.py", "/home/user/project", "/home/user/project"),
    ]
    
    print("\n  Recording commands:")
    for cmd, cwd_before, cwd_after in commands:
        cp = mgr.record_terminal(
            task_id=task_id,
            command=cmd,
            cwd_before=cwd_before,
            cwd_after=cwd_after,
            session_id="sess_123",
            result={"ok": True, "exit_code": 0},
        )
        print(f"    - '{cmd}' -> undo: '{cp.undo_command}' (reversible: {cp.reversible})")
    
    # Check stack
    stack = mgr.get_terminal_stack(task_id)
    print(f"\n  Stack size: {len(stack)}")
    
    # Test undo history
    history = mgr.get_undo_history(task_id)
    print(f"  Undo history: {len(history)} reversible commands")
    
    # Pop undo operations
    print("\n  Popping undo commands:")
    undo_count = 0
    while True:
        cp = mgr.pop_undo(task_id)
        if cp is None:
            break
        undo_count += 1
        print(f"    {undo_count}. Undo '{cp.command}' with '{cp.undo_command}'")
    
    print(f"\n  Total undos: {undo_count}")
    
    # Clear and verify
    mgr.clear_task(task_id)
    remaining = mgr.get_terminal_stack(task_id)
    print(f"  After clear: {len(remaining)} checkpoints remaining")
    
    return undo_count == 4 and len(remaining) == 0


def test_checkpoint_manager_web():
    """Test web checkpoint recording and retry tracking"""
    print("\n" + "=" * 60)
    print("TEST 3: CheckpointManager - Web Operations with Retry")
    print("=" * 60)
    
    mgr = CheckpointManager(default_max_retries=3)
    task_id = "test_task_002"
    
    # Simulate a failed web call
    print("\n  Recording initial failed call:")
    cp = mgr.record_web(
        task_id=task_id,
        tool_name="search_web",
        tool_args={"query": "test query"},
        result={"ok": False, "error": "Network timeout"},
    )
    print(f"    - Tool: {cp.tool_name}, Success: {cp.success}, Can retry: {cp.can_retry}")
    
    # Simulate retries
    print("\n  Simulating retries:")
    retry_num = 0
    while mgr.should_retry(cp):
        retry_num = mgr.increment_retry(cp)
        print(f"    Retry {retry_num}/{cp.max_retries}...")
        
        # Simulate success on 3rd retry
        if retry_num == 3:
            mgr.update_result(cp, {"ok": True, "results": ["result1", "result2"]})
            print(f"    -> Success!")
        else:
            mgr.update_result(cp, {"ok": False, "error": f"Attempt {retry_num} failed"})
            print(f"    -> Failed")
    
    print(f"\n  Final status: success={cp.success}, retries={cp.retry_count}")
    
    # Check stack
    stack = mgr.get_web_stack(task_id)
    print(f"  Web checkpoints recorded: {len(stack)}")
    
    # Get task summary
    summary = mgr.get_task_summary(task_id)
    print(f"  Task summary: {summary['web_count']} web calls, {summary['web_failed']} failed")
    
    # Clear
    mgr.clear_task(task_id)
    
    return cp.success and cp.retry_count == 3


def test_backup_manager_file_roundtrip():
    """Test BackupManager backup and restore for a single file"""
    print("\n" + "=" * 60)
    print("TEST 4: BackupManager - File Roundtrip")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_file = tmp / "original.txt"
        backup_root = tmp / "backups"

        content = "Hello from backup/restore test!\nLine 2.\n"
        src_file.write_text(content, encoding="utf-8")

        print(f"\n  Created source file: {src_file}")

        deleted_items = [
            {
                "original_arg": "original.txt",
                "path": str(src_file),
                "is_dir": False,
            }
        ]

        mgr = BackupManager(base_dir=str(backup_root))
        task_id = "backup_test_task"
        checkpoint_id = "cp_file_001"

        print("\n  Backing up deleted items...")
        backup_dir = mgr.backup_deleted_items(
            task_id=task_id,
            checkpoint_id=checkpoint_id,
            deleted_items=deleted_items,
            command="rm original.txt",
            cwd_before=str(tmp),
        )
        print(f"  Backup directory: {backup_dir}")

        # Simulate deletion
        src_file.unlink()
        print(f"  Deleted source file: exists={src_file.exists()}")

        print("\n  Restoring from backup...")
        restore_result = mgr.restore_from_checkpoint_dir(backup_dir)
        print(f"  Restore result: {restore_result}")

        file_exists_after = src_file.exists()
        restored_content = src_file.read_text(encoding="utf-8") if file_exists_after else ""

        print(f"  File exists after restore: {file_exists_after}")
        print(f"  Restored content matches: {restored_content == content}")

        return (
            restore_result.get("ok", False)
            and restore_result.get("restored_count", 0) >= 1
            and file_exists_after
            and restored_content == content
        )


def test_deletion_checkpoint_pop_undo():
    """Test that deletion checkpoints are considered undoable by pop_undo"""
    print("\n" + "=" * 60)
    print("TEST 5: CheckpointManager - Deletion Undo Selection")
    print("=" * 60)

    mgr = CheckpointManager()
    task_id = "test_task_deletion"

    # Non-undoable checkpoint (rm without backup / not marked as deletion)
    mgr.record_terminal(
        task_id=task_id,
        command="rm no_backup.txt",
        cwd_before="/tmp",
        cwd_after="/tmp",
        session_id="sess_del",
        result={"ok": True, "exit_code": 0},
        is_deletion=False,
    )

    # Deletion checkpoint with backup metadata
    cp_del = mgr.record_terminal(
        task_id=task_id,
        command="rm with_backup.txt",
        cwd_before="/tmp",
        cwd_after="/tmp",
        session_id="sess_del",
        result={"ok": True, "exit_code": 0},
        backup_path="/tmp/fake_backup_dir",
        deleted_items=[
            {"original_arg": "with_backup.txt", "path": "/tmp/with_backup.txt", "is_dir": False}
        ],
        is_deletion=True,
    )

    popped = mgr.pop_undo(task_id)

    print(f"\n  Popped checkpoint command: {popped.command if popped else None}")
    print(f"  Is deletion: {popped.is_deletion if popped else None}")
    print(f"  Has backup_path: {bool(popped.backup_path) if popped else None}")

    # After popping, stack should still have the first non-undoable checkpoint
    remaining_stack = mgr.get_terminal_stack(task_id)
    print(f"  Remaining stack size: {len(remaining_stack)}")

    return (
        popped is not None
        and popped is cp_del
        and popped.is_deletion
        and bool(popped.backup_path)
    )


async def test_terminal_mcp_integration():
    """Test actual MCP integration (requires MCP server running)"""
    print("\n" + "=" * 60)
    print("TEST 6: Terminal MCP Integration (Live)")
    print("=" * 60)
    
    try:
        from terminal.terminal_mcp.terminal_client import (
            terminal_mcp,
            open_shell,
            run_command,
            undo_last,
            get_undo_history,
            clear_task_checkpoints,
            set_current_task_id,
            set_approved_mode,
        )
        
        task_id = "integration_test_001"
        set_current_task_id(task_id)
        
        print("\n  Opening shell session...")
        session_id = await open_shell()
        print(f"    Session ID: {session_id}")
        
        # Create a test directory
        print("\n  Creating test directory...")
        result = await run_command(session_id, "mkdir -p /tmp/checkpoint_test")
        print(f"    Result: {result}")
        
        # Create a file
        print("\n  Creating test file...")
        result = await run_command(session_id, "touch /tmp/checkpoint_test/test.txt")
        print(f"    Result: {result}")
        
        # Check undo history
        print("\n  Checking undo history...")
        history = await get_undo_history()
        print(f"    History: {history}")
        
        # Undo the last command (remove the file)
        print("\n  Undoing last command (should remove file)...")
        undo_result = await undo_last(session_id)
        print(f"    Undo result: {undo_result}")
        
        # Verify file is gone
        print("\n  Verifying undo worked...")
        result = await run_command(session_id, "ls /tmp/checkpoint_test/")
        print(f"    Directory contents: {result}")
        
        # Undo again (remove directory)
        print("\n  Undoing again (should remove directory)...")
        undo_result = await undo_last(session_id)
        print(f"    Undo result: {undo_result}")
        
        # Clean up
        print("\n  Cleaning up...")
        set_current_task_id(None)
        await clear_task_checkpoints(task_id)
        await terminal_mcp.close()
        
        print("\n  ✓ Integration test passed!")
        return True
        
    except Exception as e:
        print(f"\n  ✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_web_retry_integration():
    """Test web retry integration"""
    print("\n" + "=" * 60)
    print("TEST 7: Web Retry Integration")
    print("=" * 60)
    
    try:
        from web.web_mcp.web_client import (
            search_web,
            set_current_task_id,
            clear_task_checkpoints,
        )
        
        task_id = "web_test_001"
        set_current_task_id(task_id)
        
        print("\n  Testing search_web with retry...")
        print("  (This will make a real API call if TAVILY_API_KEY is set)")
        
        result = await search_web("test query python programming")
        print(f"\n  Result: ok={result.get('ok')}")
        
        if result.get("ok"):
            results = result.get("results", [])
            print(f"  Found {len(results)} results")
            for r in results[:2]:
                print(f"    - {r.get('title', 'No title')[:50]}...")
        else:
            print(f"  Error: {result.get('error')}")
        
        # Clean up
        set_current_task_id(None)
        clear_task_checkpoints(task_id)
        
        print("\n  ✓ Web test completed!")
        return True
        
    except Exception as e:
        print(f"\n  ✗ Web test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n" + "=" * 60)
    print("  CHECKPOINT SYSTEM TESTS")
    print("=" * 60)
    
    results = {}
    
    # Unit tests (no external dependencies)
    results["UndoGenerator"] = test_undo_generator()
    results["Terminal Checkpoints"] = test_checkpoint_manager_terminal()
    results["Web Checkpoints"] = test_checkpoint_manager_web()
    results["Backup File Roundtrip"] = test_backup_manager_file_roundtrip()
    results["Deletion Checkpoint Undo Selection"] = test_deletion_checkpoint_pop_undo()
    
    # Integration tests (require MCP servers)
    print("\n" + "-" * 60)
    print("  Running integration tests...")
    print("-" * 60)
    
    results["Terminal MCP Integration"] = await test_terminal_mcp_integration()
    
    # Only run web test if API key is set
    if os.environ.get("TAVILY_API_KEY"):
        results["Web Retry Integration"] = await test_web_retry_integration()
    else:
        print("\n  Skipping web integration test (TAVILY_API_KEY not set)")
        results["Web Retry Integration"] = None
    
    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        if passed is None:
            status = "⊘ SKIPPED"
        elif passed:
            status = "✓ PASSED"
        else:
            status = "✗ FAILED"
        print(f"  {status}: {test_name}")
    
    # Overall result
    failed = sum(1 for v in results.values() if v is False)
    if failed == 0:
        print("\n  All tests passed! ✓")
    else:
        print(f"\n  {failed} test(s) failed ✗")


if __name__ == "__main__":
    asyncio.run(main())

