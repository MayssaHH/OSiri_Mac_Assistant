"""
OSiri Siri-Style UI
A compact floating command bar with fading responses
"""

import os
import json
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import httpx
import uvicorn
from dotenv import load_dotenv

load_dotenv()

ORCHESTRATOR_URL = os.getenv("A2A_BASE_URL", "http://127.0.0.1:9997/")

app = FastAPI(title="OSiri Siri UI")

pending_approvals = {}

# In-memory session memory: session_id -> list of {role, content}
# Provides short-term conversational context within a session
session_memory = {}


async def send_to_orchestrator(message: str, approved: bool = False) -> dict:
    """Send a message to the OSiri orchestrator."""
    try:
        from a2a.client import A2ACardResolver, A2AClient
        from a2a.types import MessageSendParams, SendMessageRequest
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=120)) as hc:
            resolver = A2ACardResolver(httpx_client=hc, base_url=ORCHESTRATOR_URL)
            card = await resolver.get_agent_card()
            # Override the URL from agent card (Docker uses internal hostname)
            card.url = ORCHESTRATOR_URL
            client = A2AClient(httpx_client=hc, agent_card=card)
            
            parts = []
            if approved:
                parts.append({"kind": "data", "data": {"approved": True}})
            parts.append({"kind": "text", "text": message})
            
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
            return extract_response(resp_dict)
            
    except Exception as e:
        return {"error": str(e), "ok": False}


def extract_response(resp_dict: dict) -> dict:
    """Extract the meaningful response."""
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


def format_response(response: dict) -> dict:
    """Format for frontend."""
    if "error" in response:
        return {"type": "error", "content": response["error"], "ok": False}
    
    if response.get("ok") is False and response.get("reason") == "approval_required":
        pending = response.get("pending_subtask", {})
        return {
            "type": "approval",
            "content": {
                "agent": pending.get("agent", "action"),
                "task": pending.get("task", "")
            },
            "ok": False
        }
    
    if "final_answer" in response:
        return {"type": "success", "content": response["final_answer"], "ok": True}
    
    if "raw_text" in response:
        return {"type": "success", "content": response["raw_text"], "ok": True}
    
    if "message" in response:
        return {"type": "success", "content": response.get("message"), "ok": True}
    
    return {"type": "info", "content": json.dumps(response, indent=2), "ok": response.get("ok", True)}


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """Handle chat messages with in-memory session history."""
    data = await request.json()
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    
    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    
    # Initialize session memory if needed
    if session_id not in session_memory:
        session_memory[session_id] = []
    
    approved = False
    actual_message = message
    
    if message.lower() in ["approve", "yes", "confirm", "ok"]:
        if session_id in pending_approvals and pending_approvals[session_id]["needed"]:
            approved = True
            actual_message = pending_approvals[session_id]["last_message"]
            pending_approvals[session_id]["needed"] = False
        else:
            return JSONResponse({"type": "info", "content": "Nothing to approve.", "ok": True})
    else:
        # Record user message in session memory
        session_memory[session_id].append({"role": "user", "content": actual_message})
    
    # Build conversation context from session history
    # Include previous turns so orchestrator understands references like "it", "the file", etc.
    context_parts = []
    for turn in session_memory[session_id]:
        role = turn["role"].capitalize()
        context_parts.append(f"{role}: {turn['content']}")
    
    # Send full conversation context to orchestrator
    full_context = "\n".join(context_parts)
    response = await send_to_orchestrator(full_context, approved=approved)
    
    # Extract the response content for memory
    formatted = format_response(response)
    assistant_content = formatted.get("content", "")
    if assistant_content and isinstance(assistant_content, str):
        session_memory[session_id].append({"role": "assistant", "content": assistant_content})
    
    if response.get("reason") == "approval_required":
        pending_approvals[session_id] = {"needed": True, "last_message": actual_message}
    
    return JSONResponse(formatted)


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/clear")
async def clear_session(request: Request):
    """Clear session memory to start fresh."""
    data = await request.json()
    session_id = data.get("session_id", "default")
    if session_id in session_memory:
        session_memory[session_id] = []
    if session_id in pending_approvals:
        del pending_approvals[session_id]
    return JSONResponse({"ok": True, "message": "Session cleared"})


@app.get("/", response_class=HTMLResponse)
async def index():
    return SIRI_HTML


SIRI_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSiri</title>
    <link href="https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
            background: transparent;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            align-items: center;
            padding: 20px;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }
        
        /* Response area - sits above input */
        .response-area {
            width: 100%;
            max-width: 600px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 16px;
            max-height: 60vh;
            overflow-y: auto;
            padding: 0 10px;
        }
        
        .response-area::-webkit-scrollbar {
            display: none;
        }
        
        /* Response bubble */
        .response {
            background: rgba(30, 30, 35, 0.85);
            backdrop-filter: blur(40px);
            -webkit-backdrop-filter: blur(40px);
            border-radius: 20px;
            padding: 16px 20px;
            color: white;
            font-size: 15px;
            line-height: 1.5;
            box-shadow: 
                0 4px 24px rgba(0, 0, 0, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.08);
            animation: slideUp 0.3s ease-out;
            opacity: 1;
            transition: opacity 0.5s ease-out;
        }
        
        .response.fading {
            opacity: 0;
        }
        
        .response.error {
            background: rgba(239, 68, 68, 0.2);
            border-color: rgba(239, 68, 68, 0.3);
        }
        
        .response.approval {
            background: rgba(245, 158, 11, 0.2);
            border-color: rgba(245, 158, 11, 0.3);
        }
        
        /* Approval styling - sleek inline buttons */
        .approval-content {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .approval-text {
            flex: 1;
            min-width: 200px;
        }
        
        .approval-label {
            color: rgba(255, 180, 100, 0.9);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        
        .approval-task {
            color: rgba(255, 255, 255, 0.9);
            font-size: 13px;
        }
        
        .approval-buttons {
            display: flex;
            gap: 8px;
        }
        
        .approve-btn {
            background: linear-gradient(135deg, rgba(255, 107, 157, 0.9) 0%, rgba(196, 69, 105, 0.9) 100%);
            border: none;
            border-radius: 16px;
            padding: 6px 14px;
            color: white;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .approve-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 2px 12px rgba(255, 107, 157, 0.4);
        }
        
        .approve-btn svg {
            width: 12px;
            height: 12px;
            fill: currentColor;
        }
        
        .reject-btn {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            padding: 6px 12px;
            color: rgba(255, 255, 255, 0.7);
            font-size: 12px;
            font-weight: 400;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .reject-btn:hover {
            background: rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.9);
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px) scale(0.95);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }
        
        /* Siri-style input bar */
        .input-container {
            width: 100%;
            max-width: 600px;
            position: relative;
            display: flex;
            justify-content: center;
        }
        
        .input-bar {
            width: 100%;
            background: linear-gradient(
                135deg,
                rgba(120, 50, 80, 0.7) 0%,
                rgba(60, 40, 80, 0.7) 30%,
                rgba(40, 40, 70, 0.7) 60%,
                rgba(50, 50, 80, 0.7) 100%
            );
            backdrop-filter: blur(50px);
            -webkit-backdrop-filter: blur(50px);
            border-radius: 28px;
            padding: 4px;
            box-shadow: 
                0 8px 32px rgba(0, 0, 0, 0.4),
                0 2px 8px rgba(0, 0, 0, 0.2),
                inset 0 1px 0 rgba(255, 255, 255, 0.15),
                inset 0 -1px 0 rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            overflow: hidden;
        }
        
        /* Collapsed state - just the circle */
        .input-bar.collapsed {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            padding: 0;
            cursor: pointer;
        }
        
        .input-bar.collapsed .input-inner {
            padding: 8px;
            gap: 0;
        }
        
        .input-bar.collapsed #input,
        .input-bar.collapsed .send-btn {
            opacity: 0;
            width: 0;
            padding: 0;
            pointer-events: none;
        }
        
        .input-bar.collapsed .osiri-icon {
            width: 32px;
            height: 32px;
        }
        
        .input-inner {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 16px;
            transition: all 0.3s ease;
        }
        
        .osiri-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #ff6b9d 0%, #c44569 50%, #8b4089 100%);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(196, 69, 105, 0.4);
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .osiri-icon:hover {
            transform: scale(1.1);
            box-shadow: 0 4px 16px rgba(255, 107, 157, 0.5);
        }
        
        .osiri-icon svg {
            width: 18px;
            height: 18px;
            fill: white;
            transition: transform 0.3s ease;
        }
        
        .input-bar.collapsed .osiri-icon:hover svg {
            transform: scale(1.1);
        }
        
        #input {
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            color: white;
            font-size: 17px;
            font-weight: 400;
            letter-spacing: -0.2px;
            min-width: 0;
            transition: all 0.3s ease;
        }
        
        #input::placeholder {
            color: rgba(255, 255, 255, 0.6);
        }
        
        .send-btn {
            width: 36px;
            height: 36px;
            background: rgba(255, 255, 255, 0.15);
            border: none;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            opacity: 0.7;
            flex-shrink: 0;
        }
        
        .send-btn:hover {
            background: rgba(255, 255, 255, 0.25);
            opacity: 1;
        }
        
        .send-btn:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }
        
        .send-btn svg {
            width: 16px;
            height: 16px;
            fill: white;
        }
        
        /* Loading state */
        .input-bar.loading {
            animation: pulse 1.5s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% {
                box-shadow: 
                    0 8px 32px rgba(0, 0, 0, 0.4),
                    0 2px 8px rgba(0, 0, 0, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.15);
            }
            50% {
                box-shadow: 
                    0 8px 40px rgba(196, 69, 105, 0.3),
                    0 2px 8px rgba(0, 0, 0, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
            }
        }
        
        /* Quick suggestions */
        .suggestions {
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
            flex-wrap: wrap;
            justify-content: center;
        }
        
        .suggestion {
            background: rgba(30, 30, 35, 0.6);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 10px 16px;
            color: white;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .suggestion:hover {
            background: rgba(50, 50, 55, 0.7);
            transform: translateY(-1px);
        }
        
        .suggestion-icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
        }
        
        .suggestion-icon svg {
            width: 16px;
            height: 16px;
            fill: rgba(255, 107, 157, 0.9);
        }
        
        /* Typing indicator */
        .typing {
            display: none;
            align-items: center;
            gap: 8px;
            padding: 12px 16px;
            background: rgba(30, 30, 35, 0.6);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            margin-bottom: 8px;
        }
        
        .typing.visible {
            display: flex;
        }
        
        .typing-dots {
            display: flex;
            gap: 4px;
        }
        
        .typing-dot {
            width: 6px;
            height: 6px;
            background: rgba(255, 255, 255, 0.6);
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }
        
        .typing-dot:nth-child(1) { animation-delay: 0s; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
            40% { transform: scale(1.2); opacity: 1; }
        }
        
        .typing-text {
            color: rgba(255, 255, 255, 0.6);
            font-size: 13px;
        }
    </style>
</head>
<body>
    <!-- Response area -->
    <div class="response-area" id="responses"></div>
    
    <!-- Typing indicator -->
    <div class="typing" id="typing">
        <div class="typing-dots">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
        <span class="typing-text">OSiri is thinking...</span>
    </div>
    
    <!-- Quick suggestions (shown initially) -->
    <div class="suggestions" id="suggestions">
        <div class="suggestion" onclick="send('Create a folder on Desktop')">
            <span class="suggestion-icon"><svg viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg></span>
            Create folder
        </div>
        <div class="suggestion" onclick="send('Search the web for AI news')">
            <span class="suggestion-icon"><svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg></span>
            Web search
        </div>
        <div class="suggestion" onclick="send('List my recent files')">
            <span class="suggestion-icon"><svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg></span>
            Recent files
        </div>
    </div>
    
    <!-- Siri-style input bar -->
    <div class="input-container">
        <div class="input-bar" id="inputBar">
            <div class="input-inner">
                <div class="osiri-icon">
                    <svg viewBox="0 0 24 24">
                        <path d="M17.6 11.9c-.3-.9-.9-1.7-1.5-2.4-.4-.4-.8-.7-1.2-1-.3-.2-.6-.4-1-.5v-.1c.1-.1.1-.2.2-.3.4-.7.6-1.5.6-2.3 0-1.1-.4-2.1-1.1-2.9C13 1.5 12 1 10.9 1c-.9 0-1.7.3-2.4.8-.4.3-.7.6-1 1l-.1.1-.1-.1c-.3-.4-.7-.7-1.1-1C5.6 1.3 4.8 1 3.9 1 2.8 1 1.8 1.5 1.2 2.4.4 3.2 0 4.2 0 5.3c0 .8.2 1.6.6 2.3.1.1.1.2.2.3v.1c-.3.1-.7.3-1 .5-.4.3-.9.6-1.2 1-.6.7-1.2 1.5-1.5 2.4-.3.9-.5 1.8-.5 2.8v.7c0 .5.1 1 .3 1.5.2.5.4.9.8 1.3.3.4.7.7 1.2.9.5.2 1 .3 1.5.3h14c.5 0 1-.1 1.5-.3.5-.2.9-.5 1.2-.9.3-.4.6-.8.8-1.3.2-.5.3-1 .3-1.5v-.7c.1-1-.1-1.9-.4-2.8z"/>
                    </svg>
                </div>
                <input 
                    type="text" 
                    id="input" 
                    placeholder="Ask OSiri anything..."
                    onkeydown="handleKey(event)"
                    autocomplete="off"
                >
                <button class="send-btn" id="sendBtn" onclick="sendMessage()">
                    <svg viewBox="0 0 24 24">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                    </svg>
                </button>
            </div>
        </div>
    </div>

    <script>
        const sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
        let isProcessing = false;
        const FADE_DELAY = 8000; // Response fades after 8 seconds
        
        function handleKey(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }
        
        function send(text) {
            document.getElementById('input').value = text;
            sendMessage();
        }
        
        async function sendMessage() {
            const input = document.getElementById('input');
            const message = input.value.trim();
            
            if (!message || isProcessing) return;
            
            // Hide suggestions
            document.getElementById('suggestions').style.display = 'none';
            
            // Clear input
            input.value = '';
            
            // Show loading state
            isProcessing = true;
            document.getElementById('inputBar').classList.add('loading');
            document.getElementById('typing').classList.add('visible');
            document.getElementById('sendBtn').disabled = true;
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message, session_id: sessionId })
                });
                
                const data = await response.json();
                showResponse(data);
            } catch (error) {
                showResponse({ type: 'error', content: 'Connection error. Please try again.' });
            } finally {
                isProcessing = false;
                document.getElementById('inputBar').classList.remove('loading');
                document.getElementById('typing').classList.remove('visible');
                document.getElementById('sendBtn').disabled = false;
                input.focus();
            }
        }
        
        function showResponse(data) {
            const container = document.getElementById('responses');
            const div = document.createElement('div');
            div.className = `response ${data.type || ''}`;
            
            let content = data.content;
            let shouldAutoFade = true;
            
            // Handle approval type with buttons
            if (data.type === 'approval' && typeof content === 'object') {
                div.innerHTML = `
                    <div class="approval-content">
                        <div class="approval-label">⚠️ Approval Required</div>
                        <div class="approval-task"><strong>${content.agent}</strong>: ${content.task}</div>
                    </div>
                    <div class="approval-buttons">
                        <button class="approve-btn" onclick="sendApproval(this)">
                            <svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                            Approve
                        </button>
                        <button class="reject-btn" onclick="rejectAction(this)">Cancel</button>
                    </div>
                `;
                shouldAutoFade = false; // Don't auto-fade approval messages
            } else {
                if (typeof content !== 'string') {
                    content = JSON.stringify(content, null, 2);
                }
                
                // Simple formatting
                content = content
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/\\n/g, '<br>')
                    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
                
                div.innerHTML = content;
            }
            
            container.appendChild(div);
            
            // Scroll to bottom
            container.scrollTop = container.scrollHeight;
            
            // Auto-fade after delay (only for non-approval messages)
            if (shouldAutoFade) {
                setTimeout(() => {
                    div.classList.add('fading');
                    setTimeout(() => {
                        div.remove();
                        // Show suggestions again if no responses left
                        if (container.children.length === 0) {
                            document.getElementById('suggestions').style.display = 'flex';
                        }
                    }, 500);
                }, FADE_DELAY);
            }
        }
        
        async function sendApproval(btn) {
            // Disable buttons
            const parent = btn.closest('.response');
            const buttons = parent.querySelectorAll('button');
            buttons.forEach(b => b.disabled = true);
            btn.textContent = 'Approving...';
            
            // Remove the approval message
            parent.classList.add('fading');
            setTimeout(() => parent.remove(), 500);
            
            // Send approval
            document.getElementById('input').value = 'approve';
            await sendMessage();
        }
        
        function rejectAction(btn) {
            const parent = btn.closest('.response');
            parent.classList.add('fading');
            setTimeout(() => {
                parent.remove();
                showResponse({ type: 'info', content: 'Action cancelled.' });
            }, 500);
        }
        
        // Focus input on load
        document.getElementById('input').focus();
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7861)

