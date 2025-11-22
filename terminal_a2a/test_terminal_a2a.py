import asyncio
import json
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest


BASE_URL = "http://127.0.0.1:9999"  # change if your A2A_BASE_URL differs


def extract_agent_payload(resp_dict):
    """
    Your server returns one agent text message containing JSON.
    This pulls that text out and tries to json.loads it.
    """
    # Typical SendMessageSuccessResponse shape:
    # {"jsonrpc":"2.0","id":"...","result":{"type":"message","role":"agent","parts":[{"type":"text","text":"..."}]}}
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


async def send_task(task_text: str, approved: bool = False):
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as httpx_client:
        # 1) Discover agent card
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=BASE_URL)
        agent_card = await resolver.get_agent_card()

        print(f"\nDiscovered agent: {agent_card.name}")
        print("Skills:", [s.id for s in agent_card.skills])

        # 2) Init A2A client
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        # 3) Build message parts
        parts = []
        if approved:
            # data part is the official way to pass extra params
            parts.append({"kind": "data", "data": {"approved": True}})
        parts.append({"kind": "text", "text": task_text})

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": parts,
                "messageId": uuid4().hex
            }
        }

        # 4) Send
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**send_message_payload)
        )

        response = await client.send_message(request)
        resp_dict = response.model_dump(mode="json", exclude_none=True)

        return extract_agent_payload(resp_dict)


async def main():
    task = """
You are a Terminal Assistant.
Do the following carefully:

1) Create a folder on my Desktop called a2a_terminal_demo
2) cd into it
3) Create a python virtual environment named .venv
4) Activate the venv (use the correct command for macOS zsh)
5) pip install rich
6) Create a file hello.py that:
   - prints the current working directory
   - prints the python executable path (sys.executable)
   - prints a colored "Hello from A2A Terminal Agent!" using rich
7) Run hello.py
8) Show final folder contents (ls -la)

Return a short summary at the end.
""".strip()

    print("\n==============================")
    print("PHASE 1: send WITHOUT approval")
    print("==============================")
    r1 = await send_task(task_text=task, approved=False)
    print(json.dumps(r1, indent=2))

    if r1.get("reason") == "approval_required" or (not r1.get("ok", True)):
        print("\nAs expected: plan needs approval. Resending with approved=true...\n")

        print("\n==============================")
        print("PHASE 2: resend WITH approval")
        print("==============================")
        r2 = await send_task(task_text=task, approved=True)
        print(json.dumps(r2, indent=2))
    else:
        print("\nUnexpected: task executed without approval. Check risk classifier / denylist.")


if __name__ == "__main__":
    asyncio.run(main())
