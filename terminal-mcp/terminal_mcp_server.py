import os
import subprocess
import time
import uuid
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="Terminal MCP Server")

# This is a minimal safety layer that rejects commands that are known to be dangerous.
DENY_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*;\s*\}\s*;"), 
]

def _is_denied(cmd: str) -> Optional[str]:
    for pat in DENY_PATTERNS:
        if pat.search(cmd):
            return pat.pattern
    return None


# Here I am defining a dataclass to create shell sessions and store the session information.
@dataclass
class ShellSession:
    proc: subprocess.Popen
    cwd: str
    created_at: float = field(default_factory=time.time)

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, ShellSession] = {}

    def open_shell(self, cwd: Optional[str] = None, shell_path: Optional[str] = None) -> str:
        if cwd is None:
            cwd = os.path.expanduser("~")
        if shell_path is None:
            shell_path = os.environ.get("SHELL", "/bin/zsh")

        proc = subprocess.Popen(
            [shell_path, "-f"],              
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
        )

        session_id = uuid.uuid4().hex
        self.sessions[session_id] = ShellSession(proc=proc, cwd=cwd)
        return session_id

    def close_shell(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if not s:
            return False
        try:
            s.proc.terminate()
        except Exception:
            pass
        self.sessions.pop(session_id, None)
        return True

    def run_command(self, session_id: str, command: str, timeout_s: float = 20.0) -> Dict:
        s = self.sessions.get(session_id)
        if not s:
            return {"ok": False, "error": f"Unknown session_id: {session_id}"}

        denied = _is_denied(command)
        if denied:
            return {"ok": False, "error": f"Command blocked by safety policy (pattern: {denied})"}

        token = f"__MCP_DONE_{uuid.uuid4().hex}__"
        payload = f"{command}\necho {token} $?\n"

        # Send command
        try:
            s.proc.stdin.write(payload)
            s.proc.stdin.flush()
        except Exception as e:
            return {"ok": False, "error": f"Failed to write to shell: {e}"}

        output_lines = []
        start = time.time()
        exit_code = None

        token_re = re.compile(rf"^{re.escape(token)}\s+(\d+)\s*$")

        while time.time() - start < timeout_s:
            line = s.proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue

            line_stripped = line.rstrip("\n")
            m = token_re.match(line_stripped)
            if m:
                exit_code = int(m.group(1))
                return {
                    "ok": True,
                    "exit_code": exit_code,
                    "output": "\n".join(output_lines).strip()
                }

            output_lines.append(line_stripped)

        return {
            "ok": False,
            "error": f"Timeout after {timeout_s}s",
            "partial_output": "\n".join(output_lines).strip()
        }

    def list_shells(self) -> Dict[str, Dict]:
        return {
            sid: {
                "pid": s.proc.pid,
                "cwd": s.cwd,
                "created_at": s.created_at
            }
            for sid, s in self.sessions.items()
        }


manager = SessionManager()

# Here I am defining the MCP tools that will be used to interact with the shell sessions.
@mcp.tool()
def open_shell(cwd: str | None = None) -> dict:
    sid = manager.open_shell(cwd=cwd)
    return {"session_id": sid}

@mcp.tool()
def run_command(session_id: str, command: str, timeout_s: float = 20.0) -> dict:
    """
    Run a command inside a given shell session.
    Returns {ok, output, exit_code} or {ok, error}.
    """
    return manager.run_command(session_id, command, timeout_s=timeout_s)

@mcp.tool()
def close_shell(session_id: str) -> dict:
    ok = manager.close_shell(session_id)
    return {"ok": ok}

@mcp.tool()
def list_shells() -> dict:
    return manager.list_shells()

@mcp.tool()
def get_cwd(session_id: str) -> dict:
    # I define this tool to get the current working directory of a shell session.
    # This is a simple way to avoid the stale cwd problem. I might change this later to a more robust solution.

    r = manager.run_command(session_id, "pwd", timeout_s=5)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "unknown")}

    lines = [ln.strip() for ln in r["output"].splitlines() if ln.strip()]
    cwd = lines[-1] if lines else ""
    return {"ok": True, "cwd": cwd}

def main():
    mcp.run()

if __name__ == "__main__":
    main()
