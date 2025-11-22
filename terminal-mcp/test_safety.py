import json
import anyio
from pathlib import Path

from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from mcp import StdioServerParameters


def unwrap(result):
    """Turn MCP CallToolResult into a Python dict."""
    text = ""
    for c in result.content:
        if getattr(c, "type", None) == "text":
            text += c.text
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text}


async def main():
    # Spawn the MCP server over stdio
    server_params = StdioServerParameters(
        command="python3",
        args=["terminal_mcp_server.py"],
        env=None,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) List tools
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            # 2) Open one shell session
            res = await session.call_tool("open_shell", {})
            sid = unwrap(res)["session_id"]
            print("\nSession:", sid)

            # -------------------------
            # SAFE REQUEST
            # -------------------------
            print("\n=== SAFE TEST ===")
            desktop = str(Path.home() / "Desktop")
            safe_cmds = [
                f"cd '{desktop}'",
                "mkdir -p mcp_safety_test",
                "cd mcp_safety_test",
                "echo OK > safe.txt",
                "ls"
            ]

            for cmd in safe_cmds:
                r = unwrap(await session.call_tool("run_command", {
                    "session_id": sid,
                    "command": cmd
                }))
                print(f"\n$ {cmd}")
                print(r)
                assert r.get("ok") is True, f"Safe command failed unexpectedly: {cmd}"

            print("\n✅ Safe test passed (commands executed).")

            # -------------------------
            # UNSAFE REQUESTS
            # -------------------------
            print("\n=== UNSAFE TESTS ===")

            unsafe_cmds = [
                # Hard-deny patterns (should always block)
                ("sudo ls", "denylist"),
                ("rm -rf /", "denylist"),

                # Medium risk (should require approval)
                ("pip install numpy", "risk_gate"),

                # High risk but not denylisted (should require approval)
                ("rm -rf safe.txt", "risk_gate"),
            ]

            for cmd, kind in unsafe_cmds:
                r = unwrap(await session.call_tool("run_command", {
                    "session_id": sid,
                    "command": cmd
                }))

                print(f"\n$ {cmd}  [{kind}]")
                print(r)

                assert r.get("ok") is False, f"Unsafe command was not blocked: {cmd}"

                if kind == "denylist":
                    assert "blocked" in r.get("error", "").lower(), "Expected denylist block message."

                if kind == "risk_gate":
                    assert "approval" in r.get("error", "").lower(), "Expected approval-required message."
                    assert r.get("risk") in {"medium", "high"}, "Expected medium/high risk label."

            print("\n✅ Unsafe tests passed (all blocked/refused as expected).")

            # close session
            await session.call_tool("close_shell", {"session_id": sid})


if __name__ == "__main__":
    anyio.run(main)
