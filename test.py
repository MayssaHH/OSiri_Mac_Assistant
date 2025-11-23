import asyncio
import json
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest


ORCH_URL = "http://127.0.0.1:9988/"  # orchestrator base URL


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


async def run_task(client, task_text):
    """Run a complex task with approval loop if needed."""
    pretty_print("USER TASK", {"task": task_text})

    # Phase 1: without approval
    res1 = await send_to_orchestrator(client, task_text, approved=False)
    pretty_print("PHASE 1 RESPONSE (no approval)", res1)

    # If orchestrator stops for approval, resend
    if res1.get("reason") == "approval_required":
        print("\nApproval required. Resending SAME task with approved=true...\n")
        res2 = await send_to_orchestrator(client, task_text, approved=True)
        pretty_print("PHASE 2 RESPONSE (approved)", res2)
        return res2

    return res1


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as hc:
        # Discover orchestrator card
        resolver = A2ACardResolver(httpx_client=hc, base_url=ORCH_URL)
        card = await resolver.get_agent_card()

        print(f"\nDiscovered orchestrator: {card.name}")
        print("Skills:", [s.id for s in card.skills])

        # Build client
        client = A2AClient(httpx_client=hc, agent_card=card)

        # -----------------------------
        # Complex multi-agent scenarios
        # -----------------------------
        tasks = [
            # 1) Classic split: web -> web -> terminal
            """
            Find the last article I read today,
            summarize it in 7 bullet points, then save the summary in a file called
            last_paper_summary.txt on my Desktop.
            """.strip()
         ]

        for i, t in enumerate(tasks, start=1):
            print(f"\n\n###############################")
            print(f"### RUNNING COMPLEX TASK {i} ###")
            print(f"###############################\n")
            await run_task(client, t)


if __name__ == "__main__":
    asyncio.run(main())
