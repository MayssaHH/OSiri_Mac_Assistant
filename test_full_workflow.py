"""
Comprehensive test script for the full OSiri workflow.

This script tests:
1. Gmail functionality (direct API calls)
2. Slack functionality (direct API calls)
3. App agent through orchestrator (Gmail and Slack tasks)
4. Terminal agent through orchestrator (simple example)
5. Web agent through orchestrator (simple example)
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest
from dotenv import load_dotenv

# Add app directory to path for imports
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir / "app"))

load_dotenv()

# Configuration
ORCH_URL = os.getenv("A2A_BASE_URL")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_TEST_CHANNEL", "#trying-bot")
TEST_EMAIL = os.getenv("TEST_EMAIL", "mcs12@mail.aub.edu")

# ============================================================================
# Helper Functions
# ============================================================================

def extract_agent_payload(resp_dict):
    """Extract JSON payload from A2A response."""
    if "error" in resp_dict:
        return {"error": resp_dict["error"], "raw_response": resp_dict}
    
    result = resp_dict.get("result") or {}
    parts = result.get("parts") or []
    
    text = None
    for p in parts:
        if p.get("kind") == "text" or p.get("type") == "text":
            text = p.get("text", "").strip()
            break
    
    if text is None:
        return {"raw_response": resp_dict}
    
    try:
        return json.loads(text)
    except Exception:
        return {"raw_text": text}


async def send_to_orchestrator(client, text, approved=False):
    """Send a task to the orchestrator."""
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


# ============================================================================
# Test 1: Direct Gmail API Test
# ============================================================================

def test_gmail_direct():
    """Test Gmail API directly (from test_gmail.py)."""
    print("\n" + "="*80)
    print("TEST 1: Direct Gmail API Test")
    print("="*80)
    
    try:
        # Import from app directory
        sys.path.insert(0, str(root_dir / "app"))
        from test_gmail import get_service, read_recent_emails
        
        service = get_service()
        if not service:
            print("❌ Failed to get Gmail service. Check OAuth credentials.")
            return False
        
        print("\n✓ Gmail service initialized")
        read_recent_emails(service, limit=3)
        print("\n✓ Gmail read test completed")
        return True
    except Exception as e:
        print(f"❌ Gmail direct test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# Test 2: Direct Slack API Test
# ============================================================================

async def test_slack_direct():
    """Test Slack API directly (from test_slack.py)."""
    print("\n" + "="*80)
    print("TEST 2: Direct Slack API Test")
    print("="*80)
    
    if not SLACK_BOT_TOKEN:
        print("❌ SLACK_BOT_TOKEN not set. Skipping Slack direct test.")
        return None
    
    try:
        from slack_sdk.web.async_client import AsyncWebClient
        from slack_sdk.errors import SlackApiError
        
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        
        # Resolve channel name to ID
        channel_id = None
        channel_name = SLACK_CHANNEL.lstrip("#")
        
        try:
            cursor = None
            while True:
                response = await client.conversations_list(
                    cursor=cursor, 
                    types="public_channel,private_channel"
                )
                for channel in response["channels"]:
                    if channel["name"] == channel_name:
                        channel_id = channel["id"]
                        break
                if channel_id or not response.get("response_metadata", {}).get("next_cursor"):
                    break
                cursor = response["response_metadata"]["next_cursor"]
        except SlackApiError:
            pass
        
        target = channel_id if channel_id else SLACK_CHANNEL
        
        # Send test message
        print(f"\n📤 Sending test message to {target}...")
        response = await client.chat_postMessage(
            channel=target,
            text="Hello! This is a test message from test_full_workflow.py"
        )
        print(f"✓ Message sent! Timestamp: {response['ts']}")
        
        # Read messages
        print(f"\n📥 Reading recent messages from {target}...")
        response = await client.conversations_history(channel=target, limit=3)
        messages = response["messages"]
        print(f"✓ Retrieved {len(messages)} messages")
        for msg in messages[:3]:
            text = msg.get("text", "")[:60]
            print(f"   - {text}...")
        
        print("\n✓ Slack direct test completed")
        return True
    except Exception as e:
        print(f"❌ Slack direct test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# Test 3: App Agent via Orchestrator - Gmail
# ============================================================================

async def test_app_agent_gmail(client):
    """Test app agent through orchestrator for Gmail tasks."""
    print("\n" + "="*80)
    print("TEST 3: App Agent via Orchestrator - Gmail")
    print("="*80)
    
    task = "Check my emails and give me a summary of the last 3 emails"
    
    print(f"\n📧 Task: {task}")
    result = await send_to_orchestrator(client, task, approved=False)
    
    if "error" in result:
        print(f"❌ Error: {result.get('error', {}).get('message', 'Unknown error')}")
        return False
    
    print("\n✓ Response received:")
    print(json.dumps(result, indent=2))
    
    # Check if it succeeded
    if result.get("ok"):
        print("\n✓ App agent Gmail test completed successfully")
        return True
    else:
        print("\n⚠ App agent Gmail test returned non-ok status")
        return False


# ============================================================================
# Test 4: App Agent via Orchestrator - Slack
# ============================================================================

async def test_app_agent_slack(client):
    """Test app agent through orchestrator for Slack tasks."""
    print("\n" + "="*80)
    print("TEST 4: App Agent via Orchestrator - Slack")
    print("="*80)
    
    if not SLACK_BOT_TOKEN:
        print("⚠ SLACK_BOT_TOKEN not set. Skipping Slack orchestrator test.")
        return None
    
    task = f"Send a Slack message to {SLACK_CHANNEL} saying 'Hello from OSiri orchestrator test!'"
    
    print(f"\n💬 Task: {task}")
    result = await send_to_orchestrator(client, task, approved=False)
    
    if "error" in result:
        print(f"❌ Error: {result.get('error', {}).get('message', 'Unknown error')}")
        return False
    
    print("\n✓ Response received:")
    print(json.dumps(result, indent=2))
    
    if result.get("ok"):
        print("\n✓ App agent Slack test completed successfully")
        return True
    else:
        print("\n⚠ App agent Slack test returned non-ok status")
        return False


# ============================================================================
# Test 5: Terminal Agent via Orchestrator
# ============================================================================

async def test_terminal_agent(client):
    """Test terminal agent through orchestrator."""
    print("\n" + "="*80)
    print("TEST 5: Terminal Agent via Orchestrator")
    print("="*80)
    
    task = """
    Create a file called test_terminal.txt on my Desktop with the content "Hello from terminal agent test".
    Then list the Desktop directory to confirm the file was created.
    """.strip()
    
    print(f"\n💻 Task: {task}")
    result = await send_to_orchestrator(client, task, approved=False)
    
    if "error" in result:
        print(f"❌ Error: {result.get('error', {}).get('message', 'Unknown error')}")
        return False
    
    # Check if approval is required
    if result.get("reason") == "approval_required":
        print("\n⚠ Terminal task requires approval. Resending with approved=true...")
        result = await send_to_orchestrator(client, task, approved=True)
    
    print("\n✓ Response received:")
    print(json.dumps(result, indent=2))
    
    if result.get("ok"):
        print("\n✓ Terminal agent test completed successfully")
        return True
    else:
        print("\n⚠ Terminal agent test returned non-ok status")
        return False


# ============================================================================
# Test 6: Web Agent via Orchestrator
# ============================================================================

async def test_web_agent(client):
    """Test web agent through orchestrator."""
    print("\n" + "="*80)
    print("TEST 6: Web Agent via Orchestrator")
    print("="*80)
    
    task = "Search the web for 'Python async programming' and give me a 3-bullet summary"
    
    print(f"\n🌐 Task: {task}")
    result = await send_to_orchestrator(client, task, approved=False)
    
    if "error" in result:
        print(f"❌ Error: {result.get('error', {}).get('message', 'Unknown error')}")
        return False
    
    print("\n✓ Response received:")
    print(json.dumps(result, indent=2))
    
    if result.get("ok"):
        print("\n✓ Web agent test completed successfully")
        return True
    else:
        print("\n⚠ Web agent test returned non-ok status")
        return False


# ============================================================================
# Main Test Runner
# ============================================================================

async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("OSiri Full Workflow Test Suite")
    print("="*80)
    print(f"\nOrchestrator URL: {ORCH_URL}")
    print(f"Slack Channel: {SLACK_CHANNEL}")
    print(f"Test Email: {TEST_EMAIL}")
    
    results = {}
    
    # Test 1: Direct Gmail
    try:
        results["Gmail Direct"] = test_gmail_direct()
    except Exception as e:
        print(f"\n❌ Gmail direct test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results["Gmail Direct"] = False
    
    # Test 2: Direct Slack
    try:
        results["Slack Direct"] = await test_slack_direct()
    except Exception as e:
        print(f"\n❌ Slack direct test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results["Slack Direct"] = None
    
    # Setup orchestrator client for remaining tests
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as hc:
        resolver = A2ACardResolver(httpx_client=hc, base_url=ORCH_URL)
        try:
            card = await resolver.get_agent_card()
            print(f"\n✓ Discovered orchestrator: {card.name}")
            client = A2AClient(httpx_client=hc, agent_card=card)
        except Exception as e:
            print(f"\n❌ Failed to connect to orchestrator: {e}")
            print("⚠ Skipping orchestrator-based tests")
            client = None
        
        if client:
            # Test 3: App Agent - Gmail
            try:
                results["App Agent (Gmail)"] = await test_app_agent_gmail(client)
            except Exception as e:
                print(f"\n❌ App agent Gmail test failed with exception: {e}")
                import traceback
                traceback.print_exc()
                results["App Agent (Gmail)"] = False
            
            # Test 4: App Agent - Slack
            try:
                results["App Agent (Slack)"] = await test_app_agent_slack(client)
            except Exception as e:
                print(f"\n❌ App agent Slack test failed with exception: {e}")
                import traceback
                traceback.print_exc()
                results["App Agent (Slack)"] = False
            
            # Test 5: Terminal Agent
            try:
                results["Terminal Agent"] = await test_terminal_agent(client)
            except Exception as e:
                print(f"\n❌ Terminal agent test failed with exception: {e}")
                import traceback
                traceback.print_exc()
                results["Terminal Agent"] = False
            
            # Test 6: Web Agent
            try:
                results["Web Agent"] = await test_web_agent(client)
            except Exception as e:
                print(f"\n❌ Web agent test failed with exception: {e}")
                import traceback
                traceback.print_exc()
                results["Web Agent"] = False
    
    # Summary
    print("\n\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        if passed is None:
            status = "⊘ SKIPPED"
        elif passed:
            status = "✓ PASSED"
        else:
            status = "✗ FAILED"
        print(f"  {status}: {test_name}")
    
    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    skipped_count = sum(1 for v in results.values() if v is None)
    failed_count = total - passed_count - skipped_count
    
    print(f"\nTotal: {passed_count}/{total} tests passed ({skipped_count} skipped, {failed_count} failed)")
    
    if failed_count == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠ {failed_count} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())

