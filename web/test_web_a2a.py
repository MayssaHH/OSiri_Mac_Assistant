"""
Test script for Web A2A Agent
Tests the full A2A web agent (planner + executor with MCP tools)
"""
import asyncio
import json
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest


BASE_URL = "http://127.0.0.1:9998"  # Web A2A server port


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
    Send a task to the Web A2A agent and return the response.
    
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
            print(f"   Make sure the server is running: python -m web_a2a.web_a2a_server")
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


async def test_simple_search():
    """Test 1: Simple web search"""
    print("\n" + "="*60)
    print("TEST 1: Simple Web Search")
    print("="*60)
    
    task = "Find the last article I read today, and summarize it in 7 bullet points,"
    result = await send_task(task)
    
    if result:
        print("\n📥 Response:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Test failed")


async def test_search_and_scrape():
    """Test 2: Search and scrape a URL"""
    print("\n" + "="*60)
    print("TEST 2: Search and Scrape")
    print("="*60)
    
    task = "Search for Python tutorials and summarize the first result"
    result = await send_task(task)
    
    if result:
        print("\n📥 Response:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Test failed")


async def test_browser_history():
    """Test 3: Browser history (if available)"""
    print("\n" + "="*60)
    print("TEST 3: Browser History")
    print("="*60)
    
    task = "What GitHub repositories did I visit in the last 24 hours?"
    result = await send_task(task)
    
    if result:
        print("\n📥 Response:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Test failed")


async def test_custom_task():
    """Test 4: Custom task from user"""
    print("\n" + "="*60)
    print("TEST 4: Custom Task")
    print("="*60)
    
    # You can modify this task
    task = "Find information about the Python requests library and give me a brief summary"
    result = await send_task(task)
    
    if result:
        print("\n📥 Response:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Test failed")


async def main():
    """
    Main test runner.
    Run all tests or specify which test to run.
    """
    print("🌐 Web A2A Agent Test Suite")
    print("="*60)
    print(f"Server URL: {BASE_URL}")
    print("\nMake sure the server is running:")
    print("  python -m web_a2a.web_a2a_server")
    print("\nRequired environment variables:")
    print("  - OPENAI_API_KEY")
    print("  - TAVILY_API_KEY (for web search)")
    print("="*60)
    
    # Run all tests
    await test_simple_search()
    await test_search_and_scrape()
    await test_browser_history()
    await test_custom_task()
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

