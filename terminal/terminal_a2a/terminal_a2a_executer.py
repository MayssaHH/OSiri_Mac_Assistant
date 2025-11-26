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
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("terminal-a2a-executor")
logger.setLevel(logging.INFO)

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
        # Generate a unique task ID for checkpoint tracking
        task_id = f"terminal_{uuid.uuid4().hex[:8]}"
        
        # 1) Extract user text
        task_text = get_message_text(context.message)
        task_text = (task_text or "").strip()

        # 2) Extract optional structured params (like approved=True)
        approved = False
        data_parts = get_data_parts(context.message.parts)
        if data_parts:
            approved = any(bool(dp.get("approved", False)) for dp in data_parts)

        logger.info(f"[A2A] task_id={task_id}, task_text={task_text!r}, approved={approved}")

        # 3) Plan - use planner.run() to get JSON plan
        plan_res = await self.planner.run(task_text)
        plan_text = plan_res.text.strip()

        try:
            plan: Dict[str, Any] = json.loads(plan_text)
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
            
            # Clear checkpoints for this task on completion
            try:
                await clear_task_checkpoints(task_id)
                logger.info(f"[A2A] Cleared checkpoints for task {task_id}")
            except Exception as e:
                logger.warning(f"[A2A] Failed to clear checkpoints: {e}")

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
