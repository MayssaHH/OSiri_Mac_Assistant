# terminal_a2a_executor.py
import json
import logging
from typing import Any, Dict, Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.message import get_message_text, new_agent_text_message
from a2a.utils.parts import get_data_parts

from terminal_mcp.terminal_agent import build_planner_agent, build_executor_agent


logger = logging.getLogger("terminal-a2a-executor")
logger.setLevel(logging.INFO)


class TerminalAgentExecutor(AgentExecutor):
    """
    Single A2A-facing executor.
    Internally uses your Planner + Executor agents and MCP.
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # 1) Extract user text
        task_text = get_message_text(context.message)  # joins text parts safely
        task_text = (task_text or "").strip()

        # 2) Extract optional structured params (like approved=True)
        approved = False
        data_parts = get_data_parts(context.message.parts)
        if data_parts:
            # If any data part says approved=true, allow risky commands
            approved = any(bool(dp.get("approved", False)) for dp in data_parts)

        logger.info(f"[A2A] task_text={task_text!r}, approved={approved}")

        # 3) Plan
        plan: Dict[str, Any] = await self.planner.plan(task_text)
        logger.info(f"[A2A] plan={plan}")

        # Convention: planner returns something like:
        # {
        #   "commands":[{"cmd":"cd x","risk":"safe"}, ...],
        #   "requires_approval": true/false,
        #   "summary":"..."
        # }
        requires_approval = bool(plan.get("requires_approval", False))

        if requires_approval and not approved:
            # Return plan only, no execution
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

        # 4) Execute (hits MCP under the hood)
        exec_report: Dict[str, Any] = await self.executor.execute(plan)
        logger.info(f"[A2A] exec_report={exec_report}")

        # 5) Return final response
        payload = {
            "ok": True,
            "plan": plan,
            "execution": exec_report
        }

        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps(payload, indent=2))
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Optional for now
        await event_queue.enqueue_event(
            new_agent_text_message("cancel not supported for TerminalAgentExecutor")
        )
