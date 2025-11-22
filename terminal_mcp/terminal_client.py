import os, json, asyncio
from contextlib import AsyncExitStack
from typing import Optional, Annotated, Any, Dict

from pydantic import Field
from agent_framework import ai_function
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class TerminalMCPClient:
    def __init__(self, server_script_path: str):
        self.server_script_path = server_script_path
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

    async def connect(self):
        if self.session is not None:
            return

        is_python = self.server_script_path.endswith(".py")
        command = "python3" if is_python else "node"

        server_params = StdioServerParameters(
            command=command,
            args=[self.server_script_path],
            env=None,
        )

        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )
        await self.session.initialize()

    async def call_tool(self, tool_name: str, args: Dict[str, Any]):
        await self.connect()
        return await self.session.call_tool(tool_name, args)

    async def close(self):
        if self.session is not None:
            try:
                await self.exit_stack.aclose()
            except Exception:
                pass  # Ignore errors during cleanup
            finally:
                self.session = None


def unwrap_mcp_result(result):
    # I am unwrapping the MCP result to get the text content.
    if not hasattr(result, "content"):
        return result

    text = ""
    for c in result.content:
        if getattr(c, "type", None) == "text":
            text += c.text

    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return text


SERVER_PATH = "terminal_mcp_server.py"
terminal_mcp = TerminalMCPClient(SERVER_PATH)


@ai_function(
    name="open_shell",
    description="Open a new persistent shell session and return its session id."
)
async def open_shell() -> str:
    res = await terminal_mcp.call_tool("open_shell", {})
    payload = unwrap_mcp_result(res)
    return payload["session_id"] if isinstance(payload, dict) else str(payload)


@ai_function(
    name="run_command",
    description="Run a command in a specific shell session and return stdout/stderr."
)
async def run_command(
    session_id: Annotated[str, Field(description="Shell session id from open_shell")],
    command: Annotated[str, Field(description="Terminal command to execute")],
    timeout_s: Annotated[int, Field(description="Timeout in seconds")] = 30,
    approved: Annotated[bool, Field(description="Whether the command is approved")] = False
) -> str:
    res = await terminal_mcp.call_tool(
        "run_command",
        {"session_id": session_id, "command": command, "timeout_s": timeout_s, "approved": approved},
    )
    payload = unwrap_mcp_result(res)

    # The MCP server returns dicts like {"ok":true,"exit_code":0,"output":"..."}
    if isinstance(payload, dict):
        if payload.get("ok"):
            return payload.get("output", "")
        return f"Command failed: {payload}"
    return str(payload)


@ai_function(
    name="close_shell",
    description="Close a previously opened shell session."
)
async def close_shell(
    session_id: Annotated[str, Field(description="Shell session id to close")],
) -> str:
    res = await terminal_mcp.call_tool("close_shell", {"session_id": session_id})
    payload = unwrap_mcp_result(res)
    return "closed" if isinstance(payload, dict) and payload.get("ok") else str(payload)


@ai_function(
    name="list_shells",
    description="List open shell sessions."
)
async def list_shells() -> str:
    res = await terminal_mcp.call_tool("list_shells", {})
    payload = unwrap_mcp_result(res)
    return json.dumps(payload, indent=2) if isinstance(payload, dict) else str(payload)


@ai_function(
    name="get_cwd",
    description="Get current working directory for a session."
)
async def get_cwd(
    session_id: Annotated[str, Field(description="Shell session id")],
) -> str:
    res = await terminal_mcp.call_tool("get_cwd", {"session_id": session_id})
    payload = unwrap_mcp_result(res)
    return payload.get("cwd", "") if isinstance(payload, dict) else str(payload)



