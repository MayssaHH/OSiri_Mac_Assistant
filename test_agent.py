import asyncio
import httpx
import json
from uuid import uuid4
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

async def run_test():
    base_url = "http://127.0.0.1:9000"
    # task_text = "send a hello message to slack channel trying-bot"
    
    async with httpx.AsyncClient(timeout=30.0) as httpx_client:
        print(f"Connecting to {base_url}...")
        
        # 1. Discover Agent Card
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        try:
            agent_card = await resolver.get_agent_card()
            print(f"Found Agent: {agent_card.name}")
        except Exception as e:
            print(f"Failed to get agent card: {e}")
            return

        # 2. Init Client
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        # 3. Build Message
        task_text = "Check my unread emails using the 'read_email' tool and summarize them."
        parts = [{"kind": "text", "text": task_text}]
        payload = {
            "message": {
                "role": "user",
                "parts": parts,
                "messageId": uuid4().hex
            }
        }

        # 4. Send Request
        print(f"Sending task: '{task_text}'")
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**payload)
        )
        
        try:
            response = await client.send_message(request)
            
            # 5. Print Result
            resp_dict = response.model_dump(mode="json", exclude_none=True)
            
            # Extract the text from the response for readability
            print("\n--- Response ---")
            result = resp_dict.get("result", {})
            parts = result.get("parts", [])
            for p in parts:
                if p.get("type") == "text" or p.get("kind") == "text":
                    print(p.get("text"))
            
            # Also print raw JSON just in case
            # print(json.dumps(resp_dict, indent=2))
            
        except Exception as e:
            print(f"Error sending message: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
