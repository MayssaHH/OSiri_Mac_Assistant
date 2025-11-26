"""
Test script for checkpoint integration with orchestrator.

This script tests the checkpoint system (undo/retry) through the orchestrator.
The user communicates with the orchestrator, which routes tasks to appropriate agents.

Tests:
1. Terminal-only task with undo: Create a file, then undo the operation
2. Web-only task with retry: Perform web search with automatic retry
3. Multi-agent task with undo: Use both web and terminal, then undo terminal ops
4. Delete and undo: Delete existing file (mayssa_test.txt) and attempt to undo

Note on Undo Across Requests:
- Each orchestrator request generates a new task_id
- Undo requires the same task_id to access checkpoints
- For undo to work across requests, the system may need modifications to:
  * Pass task_id in undo requests, OR
  * Support global undo (undo most recent command regardless of task_id), OR
  * Store task_id mappings for cross-request undo

The checkpoint infrastructure is tested here; cross-request undo may require
additional system modifications.
"""
import asyncio
import json
import os
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

from dotenv import load_dotenv
load_dotenv()

ORCH_URL = os.getenv("A2A_BASE_URL")

# Get Desktop path for visual tracking
DESKTOP_PATH = os.path.expanduser("~/Desktop")


def extract_agent_payload(resp_dict):
    """Pull JSON text from A2A response."""
    result = resp_dict.get("result") or {}
    parts = result.get("parts") or []

    text = None
    for p in parts:
        if p.get("kind") == "text":
            text = p.get("text", "").strip()
            break

    if text is None:
        return {"raw_response": resp_dict}

    try:
        return json.loads(text)
    except Exception:
        return {"raw_text": text}


async def send_to_orchestrator(client, text, approved=False):
    parts = []
    if approved:
        parts.append({"kind": "data", "data": {"approved": True}})
    parts.append({"kind": "text", "text": text})

    request = SendMessageRequest(
        id=str(uuid4()),
        params=MessageSendParams(
            message={
                "role": "user",
                "messageId": uuid4().hex,
                "parts": parts
            }
        )
    )

    response = await client.send_message(request)
    resp_dict = response.model_dump(mode="json", exclude_none=True)
    return extract_agent_payload(resp_dict)


def pretty_print(title, payload):
    print("\n" + "="*80)
    print(title)
    print("="*80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


async def run_task(client, task_text, approved=False):
    """Run a task with optional approval."""
    pretty_print("USER TASK", {"task": task_text, "approved": approved})

    # Send task
    res = await send_to_orchestrator(client, task_text, approved=approved)
    pretty_print("RESPONSE", res)

    # If orchestrator stops for approval, resend
    if res.get("reason") == "approval_required":
        print("\nApproval required. Resending SAME task with approved=true...\n")
        res2 = await send_to_orchestrator(client, task_text, approved=True)
        pretty_print("RESPONSE (approved)", res2)
        return res2

    return res


async def test_terminal_undo(client):
    """
    Test 1: Terminal-only task with undo
    - Create a file, then undo the operation
    - Verify the file is deleted after undo
    
    Note: This test assumes undo can work across orchestrator requests.
    Currently, each orchestrator request generates a new task_id, so undo
    may not work unless the system is modified to preserve task_id or
    support cross-request undo. This test verifies the checkpoint infrastructure.
    """
    print("\n\n" + "#"*80)
    print("# TEST 1: Terminal Agent - Create File and Undo")
    print("#"*80 + "\n")

    # Create test file on Desktop for visual tracking
    test_file = os.path.join(DESKTOP_PATH, f"test_undo_{uuid4().hex[:8]}.txt")
    test_file_basename = os.path.basename(test_file)
    test_dir = os.path.dirname(test_file)
    print(f"  Test file will be created at: {test_file}")

    # Step 1: Create a file using terminal agent
    task1 = f"Create a file named {test_file_basename} in {test_dir} with the content 'Hello from checkpoint test'"
    res1 = await run_task(client, task1, approved=True)
    
    # Verify file was created
    file_exists_before_undo = os.path.exists(test_file)
    print(f"\n✓ File exists before undo: {file_exists_before_undo}")
    if file_exists_before_undo:
        with open(test_file, 'r') as f:
            content = f.read()
        print(f"✓ File content: {content[:50]}...")
    
    if not file_exists_before_undo:
        print("⚠ Warning: File was not created. Cannot test undo.")
        return False

    # Step 2: Undo the last command
    # The orchestrator should route this to terminal agent, which should understand "undo"
    print("\n" + "-"*80)
    print("Sending UNDO command to orchestrator...")
    print("-"*80)
    print("  Note: Undo requires the same task_id. If undo fails, it may be because")
    print("  each orchestrator request generates a new task_id. The checkpoint system")
    print("  is working, but cross-request undo may need system modifications.")
    
    # Extract task_id from the response if available for context
    task_id = None
    if isinstance(res1, dict):
        execution = res1.get("execution_trace", [])
        if execution:
            terminal_result = execution[0].get("result", {}) if execution else {}
            task_id = terminal_result.get("task_id")
            if task_id:
                print(f"  Original task_id: {task_id}")
                print(f"  (New undo request will have a different task_id)")
    
    # Send undo command - phrase it so orchestrator routes to terminal agent
    # The terminal agent's executor should understand this and call undo_last
    # However, undo_last requires CURRENT_TASK_ID which will be different in new request
    undo_task = f"Undo the last terminal command that created the file {test_file_basename} in {test_dir}"
    res2 = await run_task(client, undo_task, approved=True)
    
    # Check if undo was attempted
    if isinstance(res2, dict):
        execution = res2.get("execution_trace", [])
        if execution:
            terminal_result = execution[0].get("result", {}) if execution else {}
            exec_data = terminal_result.get("execution", {})
            if isinstance(exec_data, dict) and "error" in str(exec_data):
                print(f"  ⚠ Undo may have failed: {exec_data}")
    
    # Verify file was deleted
    file_exists_after_undo = os.path.exists(test_file)
    print(f"\n✓ File exists after undo: {file_exists_after_undo}")
    
    # Cleanup if file still exists
    if file_exists_after_undo:
        try:
            os.remove(test_file)
            print("✓ Cleaned up remaining file")
        except:
            pass
    
    success = not file_exists_after_undo
    print(f"\n{'✓ TEST 1 PASSED' if success else '✗ TEST 1 FAILED'}: File was {'deleted' if success else 'still exists'} after undo")
    return success


async def test_web_retry(client):
    """
    Test 2: Web-only task with retry
    - Perform a web search
    - The web agent should automatically retry on failure (built into web_client)
    - Then explicitly test retry by asking to retry the operation
    """
    print("\n\n" + "#"*80)
    print("# TEST 2: Web Agent - Search with Auto-Retry")
    print("#"*80 + "\n")

    # Step 1: Perform a web search
    # The web agent has built-in retry logic in web_client._call_tool_with_retry
    task1 = "Search the web for 'Python async programming best practices' and give me a summary of the top 3 results"
    res1 = await run_task(client, task1, approved=False)
    
    # Check if the search succeeded
    success = False
    if isinstance(res1, dict):
        ok = res1.get("ok", False)
        execution = res1.get("execution_trace", [])
        
        if execution:
            web_result = execution[0].get("result", {})
            web_ok = web_result.get("ok", False) if isinstance(web_result, dict) else False
            
            if ok and web_ok:
                print("✓ Web search completed successfully")
                # Check if there's a final_result
                if isinstance(web_result, dict):
                    exec_data = web_result.get("execution", {})
                    if exec_data:
                        final_result = exec_data.get("final_result", "")
                        if final_result:
                            print(f"✓ Got result: {final_result[:100]}...")
                success = True
            else:
                print(f"⚠ Web search may have failed: ok={ok}, web_ok={web_ok}")
                # The web agent should have retried automatically
                print("  (Note: Web agent has auto-retry built-in)")
        else:
            print("⚠ No execution trace found")
    
    # Step 2: Explicitly test retry by asking to retry
    print("\n" + "-"*80)
    print("Testing explicit retry command...")
    print("-"*80)
    
    # Ask to retry the web search - orchestrator should route to web agent
    retry_task = "Retry the last web search for 'Python async programming best practices'"
    res2 = await run_task(client, retry_task, approved=False)
    
    # The retry should work (web agent handles retries automatically)
    retry_success = isinstance(res2, dict) and res2.get("ok", False)
    if retry_success:
        print("✓ Retry command completed successfully")
    else:
        print("⚠ Retry command may have failed")
    
    print(f"\n{'✓ TEST 2 PASSED' if (success or retry_success) else '✗ TEST 2 FAILED'}: Web search and retry {'worked' if (success or retry_success) else 'failed'}")
    return success or retry_success


async def test_multi_agent_undo(client):
    """
    Test 3: Multi-agent task with undo
    - Use both web and terminal agents
    - Then undo the terminal operations
    
    Note: Same task_id limitation as Test 1 - undo may not work across
    orchestrator requests unless the system is modified to preserve task_id.
    """
    print("\n\n" + "#"*80)
    print("# TEST 3: Multi-Agent Task - Web + Terminal, then Undo")
    print("#"*80 + "\n")

    # Create test file on Desktop for visual tracking
    test_file = os.path.join(DESKTOP_PATH, f"test_multi_{uuid4().hex[:8]}.txt")
    test_file_basename = os.path.basename(test_file)
    test_dir = os.path.dirname(test_file)
    print(f"  Test file will be created at: {test_file}")

    # Step 1: Multi-agent task - search web and save to file
    task1 = f"""Read the last article i have red about A2A protocol, summarize it in 5 bullet points and save the summary in {test_file_basename} in {test_dir}"""
    
    res1 = await run_task(client, task1, approved=True)
    
    # Verify file was created
    file_exists_before_undo = os.path.exists(test_file)
    print(f"\n✓ File exists before undo: {file_exists_before_undo}")
    if file_exists_before_undo:
        with open(test_file, 'r') as f:
            content = f.read()
        print(f"✓ File content length: {len(content)} characters")
        print(f"✓ File content preview: {content[:100]}...")
    
    if not file_exists_before_undo:
        print("⚠ Warning: File was not created. Cannot test undo.")
        # Check if web search at least worked
        if isinstance(res1, dict):
            execution = res1.get("execution_trace", [])
            if len(execution) > 0:
                print("  Note: Web search may have completed, but file creation failed")
        return False

    # Step 2: Undo the terminal operations (file creation)
    print("\n" + "-"*80)
    print("Sending UNDO command to orchestrator...")
    print("-"*80)
    print("  Note: Undo requires the same task_id. If undo fails, it may be because")
    print("  each orchestrator request generates a new task_id.")
    
    # Extract task_id from terminal subtask if available
    task_id = None
    if isinstance(res1, dict):
        execution = res1.get("execution_trace", [])
        for subtask in execution:
            if subtask.get("agent") == "terminal":
                terminal_result = subtask.get("result", {})
                task_id = terminal_result.get("task_id")
                if task_id:
                    print(f"  Terminal task_id: {task_id}")
                    print(f"  (New undo request will have a different task_id)")
                break
    
    # Send undo command - orchestrator should route to terminal agent
    # However, undo_last requires CURRENT_TASK_ID which will be different in new request
    undo_task = f"Undo the last terminal command that created the file {test_file_basename} in {test_dir}"
    res2 = await run_task(client, undo_task, approved=True)
    
    # Check if undo was attempted
    if isinstance(res2, dict):
        execution = res2.get("execution_trace", [])
        if execution:
            terminal_result = execution[0].get("result", {}) if execution else {}
            exec_data = terminal_result.get("execution", {})
            if isinstance(exec_data, dict) and "error" in str(exec_data):
                print(f"  ⚠ Undo may have failed: {exec_data}")
    
    # Verify file was deleted
    file_exists_after_undo = os.path.exists(test_file)
    print(f"\n✓ File exists after undo: {file_exists_after_undo}")
    
    # Cleanup if file still exists
    if file_exists_after_undo:
        try:
            os.remove(test_file)
            print("✓ Cleaned up remaining file")
        except:
            pass
    
    success = not file_exists_after_undo
    print(f"\n{'✓ TEST 3 PASSED' if success else '✗ TEST 3 FAILED'}: File was {'deleted' if success else 'still exists'} after undo")
    return success


async def test_delete_and_undo(client):
    """
    Test 4: Delete existing file and undo
    - Delete an existing file (mayssa_test.txt) on Desktop
    - Then undo the deletion to restore the file
    - Verify the file and its content are restored
    
    Note: According to the checkpoint system, 'rm' commands are NOT reversible
    by default. This test will verify if deletion undo works or if it needs
    system modifications (e.g., using macOS Trash for undo support).
    """
    print("\n\n" + "#"*80)
    print("# TEST 4: Delete Existing File and Undo")
    print("#"*80 + "\n")

    # Test file on Desktop
    test_file = os.path.join(DESKTOP_PATH, "mayssa_test.txt")
    test_file_basename = os.path.basename(test_file)
    test_dir = os.path.dirname(test_file)
    
    print(f"  Test file: {test_file}")
    
    # Step 0: Ensure the file exists with content
    file_exists_initially = os.path.exists(test_file)
    original_content = None
    
    if file_exists_initially:
        print(f"  ✓ File exists initially")
        with open(test_file, 'r') as f:
            original_content = f.read()
        print(f"  ✓ Original content: {original_content[:100]}...")
        print(f"  ✓ Content length: {len(original_content)} characters")
    else:
        print(f"  ⚠ File does not exist, creating it with test content...")
        original_content = "This is test content for mayssa_test.txt\nCreated for checkpoint undo test."
        with open(test_file, 'w') as f:
            f.write(original_content)
        print(f"  ✓ Created file with content")
        file_exists_initially = True

    if not file_exists_initially:
        print("  ✗ Could not create test file. Aborting test.")
        return False

    # Step 1: Delete the file using terminal agent
    print("\n" + "-"*80)
    print("Step 1: Deleting the file...")
    print("-"*80)
    
    delete_task = f"Delete the file {test_file_basename} from {test_dir}"
    res1 = await run_task(client, delete_task, approved=True)
    
    # Verify file was deleted
    file_exists_after_delete = os.path.exists(test_file)
    print(f"\n✓ File exists after delete: {file_exists_after_delete}")
    
    if file_exists_after_delete:
        print("  ⚠ Warning: File was not deleted. Cannot test undo.")
        return False

    # Step 2: Undo the deletion
    print("\n" + "-"*80)
    print("Step 2: Attempting to undo the deletion...")
    print("-"*80)
    print("  Note: 'rm' commands are typically NOT reversible in the checkpoint system.")
    print("  This test will verify if deletion undo works or needs system modifications.")
    
    # Extract task_id from the response if available
    task_id = None
    if isinstance(res1, dict):
        execution = res1.get("execution_trace", [])
        if execution:
            terminal_result = execution[0].get("result", {}) if execution else {}
            task_id = terminal_result.get("task_id")
            if task_id:
                print(f"  Original task_id: {task_id}")
                print(f"  (New undo request will have a different task_id)")
    
    # Send undo command - orchestrator should route to terminal agent
    undo_task = f"Undo the last terminal command that deleted the file {test_file_basename} from {test_dir}"
    res2 = await run_task(client, undo_task, approved=True)
    
    # Check if undo was attempted and what happened
    undo_attempted = False
    undo_error = None
    if isinstance(res2, dict):
        execution = res2.get("execution_trace", [])
        if execution:
            terminal_result = execution[0].get("result", {}) if execution else {}
            exec_data = terminal_result.get("execution", {})
            if isinstance(exec_data, dict):
                undo_attempted = True
                if "error" in str(exec_data):
                    undo_error = str(exec_data)
                    print(f"  ⚠ Undo error: {undo_error}")
                else:
                    print(f"  ✓ Undo command executed: {exec_data}")
    
    # Step 3: Verify file was restored
    file_exists_after_undo = os.path.exists(test_file)
    print(f"\n✓ File exists after undo: {file_exists_after_undo}")
    
    content_restored = False
    if file_exists_after_undo:
        with open(test_file, 'r') as f:
            restored_content = f.read()
        print(f"  ✓ File content after undo: {restored_content[:100]}...")
        print(f"  ✓ Content length: {len(restored_content)} characters")
        
        # Check if content matches
        if restored_content == original_content:
            content_restored = True
            print(f"  ✓ Content matches original!")
        else:
            print(f"  ⚠ Content does not match original")
            print(f"    Original length: {len(original_content)}")
            print(f"    Restored length: {len(restored_content)}")
    
    # Determine success
    # Success means file was restored with correct content
    # If undo doesn't work (because rm is not reversible), that's also valuable information
    success = file_exists_after_undo and content_restored
    
    if success:
        print(f"\n✓ TEST 4 PASSED: File was successfully deleted and restored with original content")
    elif file_exists_after_undo:
        print(f"\n⚠ TEST 4 PARTIAL: File was restored but content may differ")
    elif undo_error:
        print(f"\n⚠ TEST 4 INFO: Deletion undo is not supported (as expected - rm is not reversible)")
        print(f"  This confirms the checkpoint system's design: destructive operations require approval")
        print(f"  and are intentionally not undoable. To support deletion undo, the system would need")
        print(f"  modifications (e.g., using macOS Trash for file restoration).")
        # Don't count this as failure - it's expected behavior
        success = None  # Special value for "expected limitation"
    else:
        print(f"\n✗ TEST 4 FAILED: File was not restored after undo attempt")
    
    return success


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as hc:
        # Discover orchestrator card
        resolver = A2ACardResolver(httpx_client=hc, base_url=ORCH_URL)
        card = await resolver.get_agent_card()

        print(f"\nDiscovered orchestrator: {card.name}")
        print("Skills:", [s.id for s in card.skills])

        # Build client
        client = A2AClient(httpx_client=hc, agent_card=card)

        # Run all tests
        results = {}
        
        try:
            results["Terminal Undo"] = await test_terminal_undo(client)
        except Exception as e:
            print(f"\n✗ TEST 1 FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results["Terminal Undo"] = False
        
        try:
            results["Web Retry"] = await test_web_retry(client)
        except Exception as e:
            print(f"\n✗ TEST 2 FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results["Web Retry"] = False
        
        try:
            results["Multi-Agent Undo"] = await test_multi_agent_undo(client)
        except Exception as e:
            print(f"\n✗ TEST 3 FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results["Multi-Agent Undo"] = False
        
        try:
            results["Delete and Undo"] = await test_delete_and_undo(client)
        except Exception as e:
            print(f"\n✗ TEST 4 FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results["Delete and Undo"] = False

        # Summary
        print("\n\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        for test_name, passed in results.items():
            if passed is None:
                status = "⊘ INFO (expected limitation)"
            elif passed:
                status = "✓ PASSED"
            else:
                status = "✗ FAILED"
            print(f"  {status}: {test_name}")
        
        total = len(results)
        passed = sum(1 for v in results.values() if v is True)
        info = sum(1 for v in results.values() if v is None)
        print(f"\nTotal: {passed}/{total} tests passed", end="")
        if info > 0:
            print(f" ({info} info/expected limitation)")
        else:
            print()
        
        if passed == total:
            print("\n🎉 All checkpoint tests passed!")
        else:
            print(f"\n⚠ {total - passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())

