"""
Web A2A Executor
Handles incoming A2A requests and executes web tasks using the planner+executor pattern.
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.message import get_message_text, new_agent_text_message

from web_mcp.web_agent import build_planner_agent, build_executor_agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("web-a2a-executor")
logger.setLevel(logging.INFO)


class WebAgentExecutor(AgentExecutor):
    """
    A2A-facing executor for web tasks.
    Uses Planner + Executor agents with MCP tools.
    """

    def __init__(self):
        super().__init__()
        # Initialize the OpenAI client
        client = OpenAIChatClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_id="gpt-4o"
        )
        # Build planner and executor agents
        self.planner = build_planner_agent(client)
        self.executor = build_executor_agent(client)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            # 1) Extract user text
            task_text = get_message_text(context.message)
            task_text = (task_text or "").strip()

            logger.info(f"[A2A] Received task: {task_text!r}")

            # 2) Plan - use planner.run() to get JSON plan
            plan_res = await self.planner.run(task_text)
            plan_text = plan_res.text.strip()

            # Strip markdown code blocks if present
            if plan_text.startswith("```"):
                lines = plan_text.split("\n")
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line (```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                plan_text = "\n".join(lines).strip()

            try:
                plan: Dict[str, Any] = json.loads(plan_text)
            except Exception as e:
                logger.error(f"[A2A] Failed to parse plan JSON: {e}\nPlan text: {plan_text}")
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Error: Planner did not return valid JSON:\n{plan_text}")
                )
                return

            logger.info(f"[A2A] plan={plan}")

            # 3) Execute - use executor.run() with plan
            exec_prompt = f"""
            User goal:
            {task_text}

            JSON plan:
            {json.dumps(plan, indent=2)}
            """.strip()

            try:
                exec_res = await self.executor.run(exec_prompt)
            except Exception as e:
                logger.error(f"[A2A] Execution failed: {e}")
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Error during execution: {repr(e)}")
                )
                return

            exec_text = exec_res.text.strip()
            try:
                exec_report = json.loads(exec_text)
            except Exception:
                exec_report = {"text": exec_text}
            logger.info(f"[A2A] exec_report={exec_report}")

            # 4) Return final response
            payload = {
                "ok": True,
                "plan": plan,
                "execution": exec_report
            }

            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(payload, indent=2))
            )
            logger.info("[A2A] Task completed successfully")
        except Exception as e:
            logger.error(f"[A2A] Unexpected error: {e}", exc_info=True)
            await event_queue.enqueue_event(
                new_agent_text_message(f"Error: {repr(e)}")
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            new_agent_text_message("cancel not supported for WebAgentExecutor")
        )

