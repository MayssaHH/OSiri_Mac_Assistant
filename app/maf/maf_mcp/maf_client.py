"""
MAF MCP Client
Wraps the MAF MCP server tools as Python functions for agents to use.
"""
import os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager
from pathlib import Path
from agent_framework import ai_function

_approved_mode = False

def set_approved_mode(approved: bool):
    """Set global approval mode for risky operations"""
    global _approved_mode
    _approved_mode = approved

def get_approved_mode() -> bool:
    """Get current approval mode"""
    return _approved_mode

# Get absolute path to the server script
_this_file = Path(__file__)
_maf_mcp_dir = _this_file.parent
SERVER_PATH = str(_maf_mcp_dir / "maf_mcp_server.py")

@asynccontextmanager
async def get_maf_mcp():
    """Create a new MCP client session"""
    # Verify server script exists
    if not os.path.exists(SERVER_PATH):
         raise FileNotFoundError(
            f"MCP server script not found: {SERVER_PATH}. "
            f"Current working directory: {os.getcwd()}"
        )

    server_params = StdioServerParameters(
        command="python",
        args=[SERVER_PATH],
        env=os.environ.copy()
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session

# ============================================================================
# Wrapped Tool Functions
# ============================================================================

@ai_function(
    name="send_slack_message",
    description="Send a message to a Slack channel."
)
async def send_slack_message(channel: str, text: str) -> dict:
    """
    Send a message to a Slack channel.
    
    Args:
        channel: Channel name or ID (e.g. "#general")
        text: Message content
    """
    async with get_maf_mcp() as session:
        result = await session.call_tool("send_slack_message", arguments={"channel": channel, "text": text})
        if result.content:
            text_resp = result.content[0].text
            return json.loads(text_resp) if isinstance(text_resp, str) else text_resp
        return {"ok": False, "error": "No response"}

@ai_function(
    name="read_slack_messages",
    description="Read recent Slack messages."
)
async def read_slack_messages(channel: str, limit: int = 10) -> dict:
    """
    Read recent Slack messages.
    
    Args:
        channel: Channel name or ID
        limit: Number of messages to read
    """
    async with get_maf_mcp() as session:
        result = await session.call_tool("read_slack_messages", arguments={"channel": channel, "limit": limit})
        if result.content:
            text_resp = result.content[0].text
            return json.loads(text_resp) if isinstance(text_resp, str) else text_resp
        return {"ok": False, "error": "No response"}

@ai_function(
    name="send_outlook_email",
    description="Send an email via Outlook."
)
async def send_outlook_email(to_email: str, subject: str, body: str) -> dict:
    """
    Send an email via Outlook.
    
    Args:
        to_email: Recipient address
        subject: Email subject
        body: Email body
    """
    async with get_maf_mcp() as session:
        result = await session.call_tool("send_outlook_email", arguments={"to_email": to_email, "subject": subject, "body": body})
        if result.content:
            text_resp = result.content[0].text
            return json.loads(text_resp) if isinstance(text_resp, str) else text_resp
        return {"ok": False, "error": "No response"}

@ai_function(
    name="read_outlook_emails",
    description="Read recent Outlook emails."
)
async def read_outlook_emails(limit: int = 5) -> dict:
    """
    Read recent Outlook emails.
    
    Args:
        limit: Number of emails to read
    """
    async with get_maf_mcp() as session:
        result = await session.call_tool("read_outlook_emails", arguments={"limit": limit})
        if result.content:
            text_resp = result.content[0].text
            return json.loads(text_resp) if isinstance(text_resp, str) else text_resp
        return {"ok": False, "error": "No response"}

