"""
Test script for MAF (Slack/Outlook) A2A Agent
Tests the full A2A MAF agent (planner + executor with MCP tools)
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx

# Add project root to sys.path to allow importing a2a
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest


BASE_URL = "http://127.0.0.1:8003"  # MAF A2A server port


def extract_agent_payload(resp_dict):
    """
    Extract the agent's response text and try to parse as JSON.
    The server returns one agent text message containing JSON.
    """
    result = resp_dict.get("result") or {}
    parts = result.get("parts") or []

    # Find first text part
    text = None
    for p in parts:
        if p.get("type") == "text" or p.get("kind") == "text":
            text = p.get("text")
            break

    if text is None:
        return {"raw_response": resp_dict}

    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {"raw_text": text}


async def send_task(task_text: str):
    """
    Send a task to the MAF A2A agent and return the response.
    
    Args:
        task_text: The task description to send to the agent
        
    Returns:
        Parsed response from the agent
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=120.0)) as httpx_client:
        # 1) Discover agent card
        print(f"🔍 Discovering agent at {BASE_URL}...")
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=BASE_URL)
        try:
            agent_card = await resolver.get_agent_card()
        except Exception as e:
            print(f"❌ Failed to discover agent: {e}")
            print(f"   Make sure the server is running: python -m maf.maf_a2a.maf_a2a_server")
            return None

        print(f"✅ Discovered agent: {agent_card.name}")
        print(f"   Skills: {[s.id for s in agent_card.skills]}")
        print(f"   Description: {agent_card.description}")

        # 2) Init A2A client
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        # 3) Build message parts
        parts = [{"kind": "text", "text": task_text}]

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": parts,
                "messageId": uuid4().hex
            }
        }

        # 4) Send message
        print(f"\n📤 Sending task: {task_text[:60]}...")
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**send_message_payload)
        )

        try:
            response = await client.send_message(request)
            resp_dict = response.model_dump(mode="json", exclude_none=True)
            return extract_agent_payload(resp_dict)
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            return None


async def test_check_messages():
    """Test 1: Check messages"""
    print("\n" + "="*60)
    print("TEST 1: Check Slack and Outlook messages")
    print("="*60)
    
    task = "Check my recent Slack messages in #trying-bot and my latest emails."
    result = await send_task(task)
    
    if result:
        print("\n📥 Response:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Test failed")


#async def test_send_slack():
#   """Test 2: Send Slack message"""
#    print("\n" + "="*60)
#   print("TEST 2: Send Slack Message")
#    print("="*60)
    
#    task = "Send a message to #general saying 'Hello from MAF Agent test!'"
#   result = await send_task(task)
  
#    if result:
#        print("\n📥 Response:")
#        print(json.dumps(result, indent=2))
#    else:
#        print("❌ Test failed")


async def test_forward_email_to_slack():
    """Test 3: Complex task (Forwarding)"""
    print("\n" + "="*60)
    print("TEST 3: Forward Email to Slack")
    print("="*60)
    
    task = "Read the last email and post a summary of it to Slack channel #trying-bot."
    result = await send_task(task)
    
    if result:
        print("\n📥 Response:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Test failed")


async def main():
    """
    Main test runner.
    """
    print("📧 MAF (Slack/Outlook) A2A Agent Test Suite")
    print("="*60)
    print(f"Server URL: {BASE_URL}")
    
    # Run tests
    await test_check_messages()
    # await test_send_slack()
    # await test_forward_email_to_slack()
    
    print("\n" + "="*60)
    print("✅ Tests completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

