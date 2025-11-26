"""
OSiri Mac Assistant - Web UI
A chat interface for OSiri powered by Gradio
"""

import os
import json
import gradio as gr
import httpx
from uuid import uuid4
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
ORCHESTRATOR_URL = os.getenv("A2A_BASE_URL", "http://127.0.0.1:9997/")


async def send_to_orchestrator(message: str, approved: bool = False) -> dict:
    """Send a message to the OSiri orchestrator via A2A protocol."""
    try:
        # Lazy import to avoid issues if a2a not installed
        from a2a.client import A2ACardResolver, A2AClient
        from a2a.types import MessageSendParams, SendMessageRequest
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=120)) as hc:
            # Discover orchestrator
            resolver = A2ACardResolver(httpx_client=hc, base_url=ORCHESTRATOR_URL)
            card = await resolver.get_agent_card()
            
            # Build client
            client = A2AClient(httpx_client=hc, agent_card=card)
            
            # Build message parts
            parts = []
            if approved:
                parts.append({"kind": "data", "data": {"approved": True}})
            parts.append({"kind": "text", "text": message})
            
            # Send request
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
            
            # Extract response
            return extract_response(resp_dict)
            
    except Exception as e:
        return {"error": str(e), "ok": False}


def extract_response(resp_dict: dict) -> dict:
    """Extract the meaningful response from A2A protocol response."""
    if "error" in resp_dict:
        return {"error": resp_dict["error"], "ok": False}
    
    result = resp_dict.get("result", {})
    parts = result.get("parts", [])
    
    text = None
    for p in parts:
        if p.get("kind") == "text" or p.get("type") == "text":
            text = p.get("text", "").strip()
            break
    
    if text is None:
        return {"raw_response": resp_dict, "ok": False}
    
    try:
        return json.loads(text)
    except Exception:
        return {"raw_text": text, "ok": True}


def format_response(response: dict) -> str:
    """Format the orchestrator response for display."""
    if "error" in response:
        return f"❌ **Error:** {response['error']}"
    
    if response.get("ok") is False and response.get("reason") == "approval_required":
        pending = response.get("pending_subtask", {})
        return (
            f"⚠️ **Approval Required**\n\n"
            f"The following action needs your approval:\n"
            f"- **Agent:** {pending.get('agent', 'unknown')}\n"
            f"- **Task:** {pending.get('task', 'unknown')}\n\n"
            f"Type **'approve'** to proceed or rephrase your request."
        )
    
    if "final_answer" in response:
        return response["final_answer"]
    
    if "raw_text" in response:
        return response["raw_text"]
    
    return json.dumps(response, indent=2)


# Track if we need approval for the last message
pending_approval = {"needed": False, "last_message": ""}


async def chat(message: str, history: list) -> str:
    """
    Main chat function for Gradio 6.x.
    
    Args:
        message: The user's input message (str)
        history: List of openai-style dicts: [{"role": "user"|"assistant", "content": str}, ...]
    
    Returns:
        str: The assistant's response
    """
    global pending_approval
    
    if not message.strip():
        return ""
    
    # Check if user is approving a pending action
    approved = False
    actual_message = message
    
    if message.lower().strip() in ["approve", "yes", "confirm", "ok"]:
        if pending_approval["needed"]:
            approved = True
            actual_message = pending_approval["last_message"]
            pending_approval["needed"] = False
        else:
            return "Nothing to approve. What would you like me to do?"
    
    # Send to orchestrator
    response = await send_to_orchestrator(actual_message, approved=approved)
    
    # Check if approval is needed
    if response.get("reason") == "approval_required":
        pending_approval["needed"] = True
        pending_approval["last_message"] = actual_message
    
    return format_response(response)


def create_ui():
    """Create the Gradio chat interface (Gradio 6.x compatible)."""
    demo = gr.ChatInterface(
        fn=chat,
        title="🍎 OSiri Assistant",
        description="Your AI-powered Mac assistant for terminal, web, and more",
        examples=[
            "Create a new folder called 'test_project' on my Desktop",
            "Search the web for the latest news about Apple",
            "List all files in my Downloads folder",
        ],
        autofocus=True,
        fill_height=True,
    )
    return demo


# Main entry point
if __name__ == "__main__":
    demo = create_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )
