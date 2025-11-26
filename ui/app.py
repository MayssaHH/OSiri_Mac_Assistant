"""
OSiri Mac Assistant - Premium Web UI
A beautiful, modern chat interface for OSiri with Siri-inspired design
"""

import os
import json
from uuid import uuid4
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
ORCHESTRATOR_URL = os.getenv("A2A_BASE_URL", "http://127.0.0.1:9997/")

app = FastAPI(title="OSiri Assistant")

# Track approval state per session (simple in-memory for demo)
pending_approvals = {}

# In-memory session memory: session_id -> list of {role, content}
# Provides short-term conversational context within a session
session_memory = {}


async def send_to_orchestrator(message: str, approved: bool = False) -> dict:
    """Send a message to the OSiri orchestrator via A2A protocol."""
    try:
        from a2a.client import A2ACardResolver, A2AClient
        from a2a.types import MessageSendParams, SendMessageRequest
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=120)) as hc:
            resolver = A2ACardResolver(httpx_client=hc, base_url=ORCHESTRATOR_URL)
            card = await resolver.get_agent_card()
            # Override URL from agent card (Docker uses internal hostname)
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


def format_response(response: dict) -> dict:
    """Format the orchestrator response for the frontend."""
    if "error" in response:
        return {
            "type": "error",
            "content": response["error"],
            "ok": False
        }
    
    if response.get("ok") is False and response.get("reason") == "approval_required":
        pending = response.get("pending_subtask", {})
        plan = response.get("plan", {})
        return {
            "type": "approval",
            "content": {
                "agent": pending.get("agent", "unknown"),
                "task": pending.get("task", "unknown"),
                "plan": plan
            },
            "ok": False
        }
    
    if "final_answer" in response:
        return {
            "type": "success",
            "content": response["final_answer"],
            "ok": True
        }
    
    if "raw_text" in response:
        return {
            "type": "success", 
            "content": response["raw_text"],
            "ok": True
        }
    
    # For structured responses, format nicely
    if "message" in response:
        return {
            "type": "success",
            "content": response.get("message", json.dumps(response, indent=2)),
            "ok": True
        }
    
    return {
        "type": "info",
        "content": json.dumps(response, indent=2),
        "ok": response.get("ok", True)
    }


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
    
    # Check for approval
    approved = False
    actual_message = message
    
    if message.lower() in ["approve", "yes", "confirm", "ok"]:
        if session_id in pending_approvals and pending_approvals[session_id]["needed"]:
            approved = True
            actual_message = pending_approvals[session_id]["last_message"]
            pending_approvals[session_id]["needed"] = False
        else:
            return JSONResponse({
                "type": "info",
                "content": "Nothing to approve. What would you like me to do?",
                "ok": True
            })
    else:
        # Record user message in session memory
        session_memory[session_id].append({"role": "user", "content": actual_message})
    
    # Build conversation context from session history
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
    
    # Track approval state
    if response.get("reason") == "approval_required":
        pending_approvals[session_id] = {
            "needed": True,
            "last_message": actual_message
        }
    
    return JSONResponse(formatted)


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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "osiri-ui"}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main UI."""
    return HTML_TEMPLATE


# Beautiful HTML Template with Siri Theme
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSiri Assistant</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0d0d12;
            --bg-secondary: rgba(30, 30, 40, 0.7);
            --bg-tertiary: rgba(40, 40, 55, 0.6);
            --bg-elevated: rgba(50, 50, 70, 0.5);
            --bg-input: rgba(35, 35, 50, 0.8);
            
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.7);
            --text-muted: rgba(255, 255, 255, 0.5);
            
            --accent-pink: #ff6b9d;
            --accent-purple: #c44569;
            --accent-deep: #8b4089;
            --accent-gradient: linear-gradient(135deg, #ff6b9d 0%, #c44569 50%, #8b4089 100%);
            
            --success: #34d399;
            --warning: #fbbf24;
            --error: #f87171;
            
            --border: rgba(255, 255, 255, 0.1);
            --border-hover: rgba(255, 255, 255, 0.2);
            
            --radius-sm: 12px;
            --radius-md: 16px;
            --radius-lg: 20px;
            --radius-xl: 28px;
            
            --blur: blur(40px);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }
        
        /* Background gradient - Siri style */
        .bg-gradient {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(ellipse at top, rgba(196, 69, 105, 0.15) 0%, transparent 50%),
                radial-gradient(ellipse at bottom right, rgba(139, 64, 137, 0.1) 0%, transparent 50%),
                radial-gradient(ellipse at bottom left, rgba(255, 107, 157, 0.08) 0%, transparent 40%),
                var(--bg-primary);
            z-index: -1;
        }
        
        /* Main container */
        .container {
            max-width: 900px;
            margin: 0 auto;
            height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 20px;
        }
        
        /* Header */
        .header {
            text-align: center;
            padding: 40px 0 30px;
            flex-shrink: 0;
        }
        
        .logo {
            display: inline-flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 12px;
        }
        
        .logo-icon {
            width: 52px;
            height: 52px;
            background: var(--accent-gradient);
            border-radius: var(--radius-md);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 32px rgba(196, 69, 105, 0.4);
        }
        
        .logo-icon svg {
            width: 28px;
            height: 28px;
            fill: white;
        }
        
        .logo-text {
            font-size: 36px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        
        .tagline {
            color: var(--text-secondary);
            font-size: 15px;
            font-weight: 400;
        }
        
        /* Chat area */
        .chat-container {
            flex: 1;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            background: var(--bg-secondary);
            backdrop-filter: var(--blur);
            -webkit-backdrop-filter: var(--blur);
            border-radius: var(--radius-xl);
            border: 1px solid var(--border);
            box-shadow: 
                0 8px 32px rgba(0, 0, 0, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        
        .messages::-webkit-scrollbar {
            width: 6px;
        }
        
        .messages::-webkit-scrollbar-track {
            background: transparent;
        }
        
        .messages::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 3px;
        }
        
        .message {
            display: flex;
            gap: 12px;
            max-width: 85%;
            animation: messageIn 0.3s ease-out;
        }
        
        @keyframes messageIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .message.user {
            align-self: flex-end;
            flex-direction: row-reverse;
        }
        
        .message-avatar {
            width: 36px;
            height: 36px;
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        
        .message.user .message-avatar {
            background: var(--accent-gradient);
        }
        
        .message.assistant .message-avatar {
            background: var(--accent-gradient);
        }
        
        .message-avatar svg {
            width: 18px;
            height: 18px;
            fill: white;
        }
        
        .message-content {
            padding: 14px 18px;
            border-radius: var(--radius-lg);
            line-height: 1.6;
            font-size: 14px;
        }
        
        .message.user .message-content {
            background: linear-gradient(135deg, rgba(196, 69, 105, 0.8) 0%, rgba(139, 64, 137, 0.8) 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .message.assistant .message-content {
            background: var(--bg-tertiary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }
        
        .message-content pre {
            background: rgba(0, 0, 0, 0.3);
            padding: 12px;
            border-radius: var(--radius-sm);
            overflow-x: auto;
            margin: 10px 0;
            font-family: 'SF Mono', 'Menlo', monospace;
            font-size: 13px;
        }
        
        .message-content code {
            font-family: 'SF Mono', 'Menlo', monospace;
            background: rgba(0, 0, 0, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
        }
        
        /* Approval card */
        .approval-card {
            background: rgba(251, 191, 36, 0.1);
            border: 1px solid rgba(251, 191, 36, 0.3);
            border-radius: var(--radius-md);
            padding: 16px;
            margin-top: 8px;
        }
        
        .approval-card h4 {
            color: var(--warning);
            font-size: 14px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .approval-detail {
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
            font-size: 13px;
        }
        
        .approval-detail .label {
            color: var(--text-muted);
            min-width: 60px;
        }
        
        .approval-detail .value {
            color: var(--text-primary);
        }
        
        /* Input area */
        .input-area {
            padding: 20px;
            border-top: 1px solid var(--border);
        }
        
        .input-wrapper {
            display: flex;
            gap: 12px;
            align-items: flex-end;
        }
        
        .input-container {
            flex: 1;
            position: relative;
        }
        
        #message-input {
            width: 100%;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 14px 18px;
            color: var(--text-primary);
            font-size: 14px;
            font-family: inherit;
            resize: none;
            outline: none;
            transition: all 0.2s ease;
            min-height: 52px;
            max-height: 150px;
        }
        
        #message-input:focus {
            border-color: var(--accent-purple);
            box-shadow: 0 0 0 3px rgba(196, 69, 105, 0.2);
        }
        
        #message-input::placeholder {
            color: var(--text-muted);
        }
        
        .send-btn {
            width: 52px;
            height: 52px;
            background: var(--accent-gradient);
            border: none;
            border-radius: var(--radius-md);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            flex-shrink: 0;
            box-shadow: 0 4px 16px rgba(196, 69, 105, 0.3);
        }
        
        .send-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(196, 69, 105, 0.4);
        }
        
        .send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .send-btn svg {
            width: 20px;
            height: 20px;
            fill: white;
        }
        
        /* Typing indicator */
        .typing-indicator {
            display: none;
            align-items: center;
            gap: 12px;
            padding: 8px 0;
        }
        
        .typing-indicator.visible {
            display: flex;
        }
        
        .typing-dots {
            display: flex;
            gap: 4px;
        }
        
        .typing-dot {
            width: 8px;
            height: 8px;
            background: var(--accent-pink);
            border-radius: 50%;
            animation: typingBounce 1.4s infinite ease-in-out;
        }
        
        .typing-dot:nth-child(1) { animation-delay: 0s; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes typingBounce {
            0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
            40% { transform: scale(1); opacity: 1; }
        }
        
        /* Welcome state */
        .welcome {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
            text-align: center;
        }
        
        .welcome-icon {
            width: 80px;
            height: 80px;
            background: var(--accent-gradient);
            border-radius: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 24px;
            box-shadow: 0 12px 40px rgba(196, 69, 105, 0.4);
        }
        
        .welcome-icon svg {
            width: 40px;
            height: 40px;
            fill: white;
        }
        
        .welcome h2 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .welcome p {
            color: var(--text-secondary);
            font-size: 15px;
            max-width: 400px;
        }
        
        .suggestions {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-top: 32px;
            width: 100%;
            max-width: 500px;
        }
        
        .suggestion {
            background: var(--bg-tertiary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 14px 18px;
            text-align: left;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 14px;
        }
        
        .suggestion:hover {
            background: var(--bg-elevated);
            border-color: var(--accent-purple);
            transform: translateX(4px);
        }
        
        .suggestion-icon {
            width: 40px;
            height: 40px;
            background: var(--bg-input);
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .suggestion-icon svg {
            width: 20px;
            height: 20px;
            fill: var(--accent-pink);
        }
        
        .suggestion-text {
            flex: 1;
        }
        
        .suggestion-text .title {
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 2px;
        }
        
        .suggestion-text .desc {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        /* Status badge */
        .status-badge {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--bg-tertiary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 8px 12px;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .status-dot {
            width: 6px;
            height: 6px;
            background: var(--success);
            border-radius: 50%;
        }
        
        /* Mobile responsive */
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header {
                padding: 20px 0;
            }
            
            .logo-text {
                font-size: 28px;
            }
            
            .message {
                max-width: 95%;
            }
            
            .suggestions {
                max-width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="bg-gradient"></div>
    
    <div class="container">
        <header class="header">
            <div class="logo">
                <div class="logo-icon">
                    <svg viewBox="0 0 24 24">
                        <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
                    </svg>
                </div>
                <span class="logo-text">OSiri</span>
            </div>
            <p class="tagline">Your intelligent Mac assistant</p>
        </header>
        
        <main class="chat-container">
            <div class="messages" id="messages">
                <div class="welcome" id="welcome">
                    <div class="welcome-icon">
                        <svg viewBox="0 0 24 24">
                            <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM13 16h-2v2h2v-2zm0-6h-2v4h2v-4z"/>
                        </svg>
                    </div>
                    <h2>How can I help you today?</h2>
                    <p>I can manage files, search the web, access your browser history, and much more.</p>
                    
                    <div class="suggestions">
                        <div class="suggestion" onclick="sendSuggestion('Create a new folder called project_files on my Desktop')">
                            <div class="suggestion-icon">
                                <svg viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
                            </div>
                            <div class="suggestion-text">
                                <div class="title">Create a folder</div>
                                <div class="desc">Organize files on your Desktop</div>
                            </div>
                        </div>
                        <div class="suggestion" onclick="sendSuggestion('Search the web for the latest AI news')">
                            <div class="suggestion-icon">
                                <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                            </div>
                            <div class="suggestion-text">
                                <div class="title">Search the web</div>
                                <div class="desc">Find the latest AI news</div>
                            </div>
                        </div>
                        <div class="suggestion" onclick="sendSuggestion('What papers did I read recently?')">
                            <div class="suggestion-icon">
                                <svg viewBox="0 0 24 24"><path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/></svg>
                            </div>
                            <div class="suggestion-text">
                                <div class="title">Check browser history</div>
                                <div class="desc">Find papers you've read</div>
                            </div>
                        </div>
                        <div class="suggestion" onclick="sendSuggestion('List files in my Downloads folder')">
                            <div class="suggestion-icon">
                                <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
                            </div>
                            <div class="suggestion-text">
                                <div class="title">List files</div>
                                <div class="desc">See what's in Downloads</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="typing-indicator" id="typing">
                <div class="message-avatar" style="background: var(--accent-gradient); width: 28px; height: 28px;">
                    <svg viewBox="0 0 24 24" style="width: 14px; height: 14px; fill: white;">
                        <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
                    </svg>
                </div>
                <div class="typing-dots">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
            
            <div class="input-area">
                <div class="input-wrapper">
                    <div class="input-container">
                        <textarea 
                            id="message-input" 
                            placeholder="Ask me anything..." 
                            rows="1"
                            onkeydown="handleKeyDown(event)"
                            oninput="autoResize(this)"
                        ></textarea>
                    </div>
                    <button class="send-btn" id="send-btn" onclick="sendMessage()">
                        <svg viewBox="0 0 24 24">
                            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                        </svg>
                    </button>
                </div>
            </div>
        </main>
    </div>
    
    <div class="status-badge">
        <div class="status-dot"></div>
        Connected to OSiri
    </div>

    <script>
        const sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
        let isProcessing = false;
        
        function autoResize(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
        }
        
        function handleKeyDown(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        }
        
        function sendSuggestion(text) {
            document.getElementById('message-input').value = text;
            sendMessage();
        }
        
        async function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message || isProcessing) return;
            
            // Hide welcome screen
            const welcome = document.getElementById('welcome');
            if (welcome) welcome.style.display = 'none';
            
            // Add user message
            addMessage(message, 'user');
            input.value = '';
            input.style.height = 'auto';
            
            // Show typing indicator
            isProcessing = true;
            document.getElementById('typing').classList.add('visible');
            document.getElementById('send-btn').disabled = true;
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message, session_id: sessionId })
                });
                
                const data = await response.json();
                addAssistantMessage(data);
            } catch (error) {
                addMessage('Sorry, I encountered an error. Please try again.', 'assistant', 'error');
            } finally {
                isProcessing = false;
                document.getElementById('typing').classList.remove('visible');
                document.getElementById('send-btn').disabled = false;
            }
        }
        
        function addMessage(content, role, type = 'normal') {
            const messages = document.getElementById('messages');
            const div = document.createElement('div');
            div.className = `message ${role}`;
            
            const avatarSvg = role === 'user' 
                ? '<svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>'
                : '<svg viewBox="0 0 24 24"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>';
            
            div.innerHTML = `
                <div class="message-avatar">${avatarSvg}</div>
                <div class="message-content">${formatContent(content)}</div>
            `;
            
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }
        
        function addAssistantMessage(data) {
            const messages = document.getElementById('messages');
            const div = document.createElement('div');
            div.className = 'message assistant';
            
            let contentHtml = '';
            
            if (data.type === 'error') {
                contentHtml = `<div style="color: var(--error);">Error: ${formatContent(data.content)}</div>`;
            } else if (data.type === 'approval') {
                const c = data.content;
                contentHtml = `
                    <div>This action requires your approval:</div>
                    <div class="approval-card">
                        <h4>Approval Required</h4>
                        <div class="approval-detail">
                            <span class="label">Agent:</span>
                            <span class="value">${c.agent}</span>
                        </div>
                        <div class="approval-detail">
                            <span class="label">Task:</span>
                            <span class="value">${c.task}</span>
                        </div>
                    </div>
                    <div style="margin-top: 12px; color: var(--text-secondary);">
                        Type <strong>"approve"</strong> to proceed or rephrase your request.
                    </div>
                `;
            } else {
                contentHtml = formatContent(data.content);
            }
            
            const avatarSvg = '<svg viewBox="0 0 24 24"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>';
            
            div.innerHTML = `
                <div class="message-avatar">${avatarSvg}</div>
                <div class="message-content">${contentHtml}</div>
            `;
            
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }
        
        function formatContent(content) {
            if (typeof content !== 'string') {
                content = JSON.stringify(content, null, 2);
            }
            
            // Escape HTML
            content = content
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            
            // Format code blocks
            content = content.replace(/```([\\s\\S]*?)```/g, '<pre>$1</pre>');
            
            // Format inline code
            content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
            
            // Format bold
            content = content.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
            
            // Format newlines
            content = content.replace(/\\n/g, '<br>');
            
            return content;
        }
        
        // Focus input on load
        document.getElementById('message-input').focus();
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
