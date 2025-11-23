import asyncio
import json
from uuid import uuid4
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

# Load .env from root directory
root_dir = Path(__file__).parent
load_dotenv(dotenv_path=root_dir / ".env")

# Get orchestrator URL with default
ORCH_URL = os.getenv("A2A_BASE_URL", "http://127.0.0.1:9997/")


def extract_agent_payload(resp_dict):
    """
    Orchestrator returns a single agent message with JSON in a text part.
    This pulls that text out and json.loads it if possible.
    Handles both success responses and error responses.
    """
    # Check for JSON-RPC error
    if "error" in resp_dict:
        return {
            "error": resp_dict["error"],
            "raw_response": resp_dict
        }
    
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


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as hc:
        # 1) Discover orchestrator card
        resolver = A2ACardResolver(httpx_client=hc, base_url=ORCH_URL)
        card = await resolver.get_agent_card()

        print(f"\nDiscovered orchestrator: {card.name}")
        print("Skills:", [s.id for s in card.skills])

        # 2) Build A2A client
        client = A2AClient(httpx_client=hc, agent_card=card)

        # ----------------------------
        # TEST 1: Terminal-like task
        # ----------------------------
        terminal_task = """
Create a folder on my Desktop called orch_demo.
Then create a file hello.py inside it that prints "hello from orchestrator".
Finally list the folder contents.
""".strip()

        print("\n==============================")
        print("TEST 1: Terminal-like task")
        print("==============================")

        r1 = await send_to_orchestrator(client, terminal_task, approved=False)
        print(json.dumps(r1, indent=2))

        # Check for errors first
        if "error" in r1:
            print(f"\n❌ Error: {r1.get('error', {}).get('message', 'Unknown error')}")
        else:
            # If terminal agent requires approval, resend with approved=true
            downstream = r1.get("downstream", {})
            if downstream.get("reason") == "approval_required":
                print("\nTerminal task needs approval. Resending with approved=true...\n")
                r1b = await send_to_orchestrator(client, terminal_task, approved=True)
                print(json.dumps(r1b, indent=2))

        # ----------------------------
        # TEST 2: Web-like task
        # ----------------------------
        web_task = """
Search the web for the main idea of the paper "Attention Is All You Need"
and give me a 4-5 bullet summary.
""".strip()

        print("\n==============================")
        print("TEST 2: Web-like task")
        print("==============================")

        r2 = await send_to_orchestrator(client, web_task, approved=False)
        print(json.dumps(r2, indent=2))
        
        # Check for errors
        if "error" in r2:
            print(f"\n❌ Error: {r2.get('error', {}).get('message', 'Unknown error')}")


if __name__ == "__main__":
    asyncio.run(main())
