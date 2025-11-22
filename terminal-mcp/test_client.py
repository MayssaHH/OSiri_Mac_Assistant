import anyio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

async def main():
    # launch our server as a subprocess over stdio
    server_params = StdioServerParameters(
        command="python",
        args=["terminal-mcp-server.py"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            sid = (await session.call_tool("open_shell", {})).content[0].text
            sid = eval(sid)["session_id"]  # small parse shortcut
            print("session:", sid)

            r1 = await session.call_tool("run_command", {
                "session_id": sid,
                "command": "pwd"
            })
            print("pwd:", r1.content[0].text)

            r_cwd = await session.call_tool("get_cwd", {"session_id": sid})
            print("get_cwd:", r_cwd.content[0].text)

            r2 = await session.call_tool("run_command", {
                "session_id": sid,
                "command": "echo hello"
            })
            print("echo:", r2.content[0].text)

            await session.call_tool("close_shell", {"session_id": sid})

anyio.run(main)
