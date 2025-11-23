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

class MafMCPClient:
    def __init__(self, server_script_path: str):
        self.server_script_path = server_script_path
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

    async def connect(self):
        if self.session is not None:
            return

        # Verify server script exists
        if not os.path.exists(self.server_script_path):
            raise FileNotFoundError(f"MCP server script not found: {self.server_script_path}")

        # Use python from the current environment
        command = sys.executable 
        
        server_params = StdioServerParameters(
            command=command,
            args=[self.server_script_path],
            env=os.environ.copy(),
        )

        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )
            await self.session.initialize()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to MAF MCP server: {e}")

    async def call_tool(self, tool_name: str, args: Dict[str, Any]):
        await self.connect()
        return await self.session.call_tool(tool_name, args)
    
    async def close(self):
        if self.session:
            await self.exit_stack.aclose()
            self.session = None

# Setup Client
_this_file = Path(__file__)
SERVER_PATH = str(_this_file.parent / "maf_mcp_server.py")
maf_mcp = MafMCPClient(SERVER_PATH)

def unwrap_mcp_result(result):
    # Handle different MCP result formats
    if hasattr(result, "content"):
        text = "".join([c.text for c in result.content if getattr(c, "type", None) == "text"])
        return text
    return str(result)

# --- AI Functions ---

@ai_function(name="read_slack", description="Read recent Slack messages from a channel.")
async def read_slack(
    channel_name: Annotated[str, Field(description="The channel name (e.g. #general)")],
    limit: Annotated[int, Field(description="Number of messages to fetch")] = 10
) -> str:
    res = await maf_mcp.call_tool("read_slack", {"channel_name": channel_name, "limit": limit})
    return unwrap_mcp_result(res)

@ai_function(name="send_slack", description="Send a message to a Slack channel.")
async def send_slack(
    channel_name: Annotated[str, Field(description="The channel name (e.g. #general)")],
    text: Annotated[str, Field(description="The message content")]
) -> str:
    res = await maf_mcp.call_tool("send_slack", {"channel_name": channel_name, "text": text})
    return unwrap_mcp_result(res)

@ai_function(name="read_email", description="Read unread emails from inbox.")
async def read_email(
    limit: Annotated[int, Field(description="Max number of emails to fetch")] = 5
) -> str:
    res = await maf_mcp.call_tool("read_email", {"limit": limit})
    return unwrap_mcp_result(res)

@ai_function(name="send_email", description="Send an email to a recipient.")
async def send_email(
    to_email: Annotated[str, Field(description="Recipient email address")],
    subject: Annotated[str, Field(description="Email subject")],
    body: Annotated[str, Field(description="Email body content")]
) -> str:
    res = await maf_mcp.call_tool("send_email", {"to_email": to_email, "subject": subject, "body": body})
    return unwrap_mcp_result(res)

