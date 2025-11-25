import os
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional, Annotated, Any, Dict
from pydantic import Field
from agent_framework import ai_function
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()

class MafMultiClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.slack_session: Optional[ClientSession] = None
        self.email_session: Optional[ClientSession] = None

    async def connect_slack(self):
        if self.slack_session is not None:
            return

        # Use standard Slack MCP server via npx
        command = "npx.cmd" if sys.platform == "win32" else "npx"
        
        server_params = StdioServerParameters(
            command=command,
            args=["-y", "@modelcontextprotocol/server-slack"],
            env=os.environ.copy(),
        )

        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            self.slack_session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            await self.slack_session.initialize()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Slack MCP server: {e}")

    async def connect_email(self):
        if self.email_session is not None:
            return

        # Use our local Python Email MCP server
        # We point to the new email_server.py file
        current_dir = Path(__file__).parent
        script_path = str(current_dir / "email_server.py")
        
        command = sys.executable
        
        server_params = StdioServerParameters(
            command=command,
            args=[script_path],
            env=os.environ.copy(),
        )

        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            self.email_session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            await self.email_session.initialize()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Email MCP server: {e}")

    async def call_slack_tool(self, tool_name: str, args: Dict[str, Any]):
        print(f"[DEBUG] Calling Slack Tool: {tool_name} with {args}")
        try:
            await self.connect_slack()
            result = await self.slack_session.call_tool(tool_name, args)
            # print(f"[DEBUG] Slack Tool Result: {result}") # Commented out to reduce noise
            return result
        except Exception as e:
            print(f"[DEBUG] Slack Tool Error: {e}")
            raise e

    async def call_email_tool(self, tool_name: str, args: Dict[str, Any]):
        print(f"[DEBUG] Calling Email Tool: {tool_name} with {args}")
        try:
            await self.connect_email()
            result = await self.email_session.call_tool(tool_name, args)
            return result
        except Exception as e:
            print(f"[DEBUG] Email Tool Error: {e}")
            raise e
    
    async def close(self):
        await self.exit_stack.aclose()
        self.slack_session = None
        self.email_session = None

# Setup Client
maf_client = MafMultiClient()

def unwrap_mcp_result(result):
    # Handle different MCP result formats
    if hasattr(result, "content"):
        text = "".join([c.text for c in result.content if getattr(c, "type", None) == "text"])
        return text
    return str(result)

# --- AI Functions: SLACK ---

@ai_function(name="slack_list_channels", description="List all public channels in the workspace.")
async def slack_list_channels() -> str:
    res = await maf_client.call_slack_tool("slack_list_channels", {}) 
    return unwrap_mcp_result(res)

@ai_function(name="slack_post_message", description="Post a message to a Slack channel.")
async def slack_post_message(
    channel_id: Annotated[str, Field(description="The channel ID (not name) to post to")],
    text: Annotated[str, Field(description="The message content")]
) -> str:
    res = await maf_client.call_slack_tool("slack_post_message", {"channel_id": channel_id, "text": text})
    return unwrap_mcp_result(res)

@ai_function(name="slack_reply_to_thread", description="Reply to a specific message thread.")
async def slack_reply_to_thread(
    channel_id: Annotated[str, Field(description="The channel ID")],
    thread_ts: Annotated[str, Field(description="The timestamp of the parent message")],
    text: Annotated[str, Field(description="The reply content")]
) -> str:
    res = await maf_client.call_slack_tool("slack_reply_to_thread", {"channel_id": channel_id, "thread_ts": thread_ts, "text": text})
    return unwrap_mcp_result(res)

@ai_function(name="slack_add_reaction", description="Add an emoji reaction to a message.")
async def slack_add_reaction(
    channel_id: Annotated[str, Field(description="The channel ID")],
    timestamp: Annotated[str, Field(description="The timestamp of the message")],
    reaction_name: Annotated[str, Field(description="The name of the emoji (without colons)")]
) -> str:
    res = await maf_client.call_slack_tool("slack_add_reaction", {"channel_id": channel_id, "timestamp": timestamp, "name": reaction_name})
    return unwrap_mcp_result(res)

@ai_function(name="slack_get_channel_history", description="Fetch recent messages from a channel.")
async def slack_get_channel_history(
    channel_id: Annotated[str, Field(description="The channel ID")],
    limit: Annotated[int, Field(description="Number of messages to fetch")] = 10
) -> str:
    res = await maf_client.call_slack_tool("slack_get_channel_history", {"channel_id": channel_id, "limit": limit})
    return unwrap_mcp_result(res)

# NEW TOOL: User Lookup
@ai_function(name="slack_get_user_profile", description="Get detailed profile information for a specific user ID.")
async def slack_get_user_profile(
    user_id: Annotated[str, Field(description="The Slack User ID (e.g. U12345678)")]
) -> str:
    # The standard tool name is typically 'users_profile_get' or similar in API, but standard MCP uses 'slack_get_user_profile' usually.
    # Let's guess 'slack_get_user_profile'. If it fails, we will check logs.
    # Actually, looking at standard MCP docs, 'slack_get_user' might be safer or 'slack_list_users'
    # Let's try to fetch the user directly.
    try:
        res = await maf_client.call_slack_tool("slack_get_user_profile", {"user_id": user_id})
    except:
        # Fallback: maybe just list all users and filter?
        # But 'slack_get_user_profile' is standard in this specific server usually.
        raise
    return unwrap_mcp_result(res)

# --- AI Functions: EMAIL ---

@ai_function(name="read_email", description="Read unread emails from inbox.")
async def read_email(
    limit: Annotated[int, Field(description="Max number of emails to fetch")] = 5
) -> str:
    res = await maf_client.call_email_tool("read_email", {"limit": limit})
    return unwrap_mcp_result(res)

@ai_function(name="send_email", description="Send an email to a recipient.")
async def send_email(
    to_email: Annotated[str, Field(description="Recipient email address")],
    subject: Annotated[str, Field(description="Email subject")],
    body: Annotated[str, Field(description="Email body content")]
) -> str:
    res = await maf_client.call_email_tool("send_email", {"to_email": to_email, "subject": subject, "body": body})
    return unwrap_mcp_result(res)
