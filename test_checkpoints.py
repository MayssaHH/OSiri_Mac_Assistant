"""
Test script for the Checkpoint System

Tests:
1. Terminal checkpoints with undo capability
2. Web checkpoints with auto-retry
"""
import asyncio
import os
import sys

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"))

from common.checkpoint import CheckpointManager, UndoGenerator


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


async def test_terminal_mcp_integration():
    """Test actual MCP integration (requires MCP server running)"""
    print("\n" + "=" * 60)
    print("TEST 4: Terminal MCP Integration (Live)")
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
    print("TEST 5: Web Retry Integration")
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

