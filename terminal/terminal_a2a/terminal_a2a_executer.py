# terminal_a2a_executor.py
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to path so we can import terminal_mcp
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.message import get_message_text, new_agent_text_message
from a2a.utils.parts import get_data_parts


from terminal_mcp.terminal_agent import build_planner_agent, build_executor_agent
from terminal_mcp.terminal_mcp_server import classify_risk
from terminal_mcp.terminal_client import (
    set_current_task_id,
    clear_task_checkpoints,
    open_shell,
    undo_last,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("terminal-a2a-executor")
logger.setLevel(logging.INFO)


def strip_markdown_json(text: str) -> str:
    """Strip markdown code block markers from JSON response."""
    text = text.strip()
    # Handle ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        # Find the end of the first line (might be ```json or just ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove trailing ```
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class TerminalAgentExecutor(AgentExecutor):
    """
    Single A2A-facing executor.
    Internally uses your Planner + Executor agents and MCP.
    """

    def __init__(self):
        super().__init__()
        # Initialize the OpenAI client
        client = OpenAIChatClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_id="gpt-4o-mini"
        )
        # Build planner and executor agents
        self.planner = build_planner_agent(client)
        self.executor = build_executor_agent(client)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # 1) Extract user text
        task_text = get_message_text(context.message)
        task_text = (task_text or "").strip()

        # Generate a unique task ID for checkpoint tracking
        task_id = f"terminal_{uuid.uuid4().hex[:8]}"

        # 2) Extract optional structured params (like approved=True)
        approved = False
        data_parts = get_data_parts(context.message.parts)
        if data_parts:
            approved = any(bool(dp.get("approved", False)) for dp in data_parts)

        logger.info(f"[A2A] task_id={task_id}, task_text={task_text!r}, approved={approved}")

        # ------------------------------------------------------------------
        # Special-case undo intent: call MCP undo_last instead of planning
        # new shell commands (e.g., rm or Trash-based recovery).
        # ------------------------------------------------------------------
        lower_text = task_text.lower()
        undo_keywords = [
            "undo the last command",
            "undo last command",
            "undo the last terminal command",
            "undo my last terminal command",
            "revert the last command",
            "revert last command",
            "recover the last command",
            "recover last command",
            "recover the file",
            "recover my file",
            "restore the file",
            "restore my file",
            "undelete the file",
            "undelete my file",
        ]
        # Check if any undo keyword is present along with indicators of "last" action
        is_undo_intent = any(k in lower_text for k in undo_keywords) and any(
            indicator in lower_text for indicator in ["last", "recent", "deleted", "file"]
        )
        
        if is_undo_intent:
            logger.info("[A2A] Detected undo intent - calling MCP undo_last directly")
            try:
                # Open a transient shell session for command-based undos
                session_id = await open_shell()
                undo_raw = await undo_last(session_id)
                try:
                    undo_payload = json.loads(undo_raw)
                except Exception:
                    undo_payload = {"raw": undo_raw}

                # Build user-friendly message
                ok = undo_payload.get("ok", False)
                if ok:
                    undone_cmd = undo_payload.get("undone_command", "")
                    restore_result = undo_payload.get("restore_result", {})
                    restored_count = restore_result.get("restored_count", 0)
                    
                    if restored_count > 0:
                        message = f"Successfully recovered {restored_count} file(s) from the command: {undone_cmd}"
                    else:
                        message = f"Successfully undid the command: {undone_cmd}"
                else:
                    message = undo_payload.get("error", "Failed to undo the last operation")

                payload = {
                    "ok": ok,
                    "task_id": task_id,
                    "message": message,
                    "undo": undo_payload,
                }

                await event_queue.enqueue_event(
                    new_agent_text_message(json.dumps(payload, indent=2))
                )
                return
            except Exception as e:
                logger.error(f"[A2A] Undo flow failed: {e}", exc_info=True)
                await event_queue.enqueue_event(
                    new_agent_text_message(
                        json.dumps(
                            {
                                "ok": False,
                                "error": f"Undo failed: {e}",
                            },
                            indent=2,
                        )
                    )
                )
                return

        # 3) Plan - use planner.run() to get JSON plan
        plan_res = await self.planner.run(task_text)
        plan_text = plan_res.text.strip()
        
        # Strip markdown code blocks if present (LLM often wraps JSON in ```json ... ```)
        plan_text_clean = strip_markdown_json(plan_text)

        try:
            plan: Dict[str, Any] = json.loads(plan_text_clean)
        except Exception as e:
            logger.error(f"[A2A] Failed to parse plan JSON: {e}\nPlan text: {plan_text}")
            await event_queue.enqueue_event(
                new_agent_text_message(f"Error: Planner did not return valid JSON:\n{plan_text}")
            )
            return

        # 3.b) Compute requires_approval from actual commands (Option B gate)
        requires_approval = False
        steps = plan.get("steps", [])

        if isinstance(steps, list):
            for st in steps:
                cmd = (st.get("command") or "").strip()
                risk = classify_risk(cmd)  # make sure classify_risk is imported/defined in this file
                st["risk"] = risk          # annotate plan for the caller
                if risk in ("medium", "high"):
                    requires_approval = True
        else:
            # fallback if planner schema changes
            requires_approval = bool(plan.get("requires_approval", False))

        plan["requires_approval"] = requires_approval  # normalize schema
        logger.info(f"[A2A] plan={plan}")

        if requires_approval and not approved:
            payload = {
                "ok": False,
                "reason": "approval_required",
                "plan": plan,
                "message": "Plan includes medium/high risk commands. Resend with approved=true to execute."
            }
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(payload, indent=2))
            )
            return

        # 4) Execute - use executor.run() with plan
        exec_prompt = f"""
        User goal:
        {task_text}

        JSON plan:
        {json.dumps(plan, indent=2)}
        """.strip()

        from terminal_mcp.terminal_client import set_approved_mode 
        
        # Set task_id and approved mode for checkpoint tracking
        set_current_task_id(task_id)
        set_approved_mode(approved)
        
        try:
            exec_res = await self.executor.run(exec_prompt)
        finally:
            # Always reset so settings don't leak to later tasks
            set_approved_mode(False)
            set_current_task_id(None)

        exec_text = exec_res.text.strip()
        try:
            exec_report = json.loads(exec_text)
        except Exception:
            exec_report = {"text": exec_text}
        logger.info(f"[A2A] exec_report={exec_report}")

        # 5) Return final response
        payload = {
            "ok": True,
            "task_id": task_id,
            "plan": plan,
            "execution": exec_report
        }

        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps(payload, indent=2))
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            new_agent_text_message("cancel not supported for TerminalAgentExecutor")
        )
