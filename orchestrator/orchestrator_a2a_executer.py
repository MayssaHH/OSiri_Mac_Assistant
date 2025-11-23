# orchestrator_a2a_executor.py
import json
import logging
import os
import sys
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.message import get_message_text, new_agent_text_message
from a2a.utils.parts import get_data_parts
from dotenv import load_dotenv

from planner import PlannerLLM, validate_plan
from synthesizer import SynthesizerLLM 

logger = logging.getLogger("orchestrator-a2a")
logger.setLevel(logging.INFO)

# Setup logging to file and console
if not logger.handlers:
    ch = logging.StreamHandler()
    fh = logging.FileHandler("orchestrator_tool_calls.log", encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    ch.setFormatter(fmt)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)

load_dotenv()

TERMINAL_URL = os.getenv("TERMINAL_AGENT_URL")
WEB_URL = os.getenv("WEB_AGENT_URL")

ALLOWED_AGENTS = ["terminal", "web"]

async def call_downstream(agent_url: str, user_text: str, data_parts: Optional[list] = None) -> Dict[str, Any]:
    logger.info(f"[call_downstream] Initiating call to agent at {agent_url}")
    logger.info(f"[call_downstream] Task text: {user_text[:100]}...")
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as hc:
        # discover agent card
        logger.info(f"[call_downstream] Discovering agent card...")
        resolver = A2ACardResolver(httpx_client=hc, base_url=agent_url)
        card = await resolver.get_agent_card()
        logger.info(f"[call_downstream] Discovered agent: {card.name}")

        # build client
        client = A2AClient(httpx_client=hc, agent_card=card)
        logger.info(f"[call_downstream] Sending message to agent...")

        # build message parts
        parts = []
        if data_parts:
            for dp in data_parts:
                parts.append({"kind": "data", "data": dp})
        parts.append({"kind": "text", "text": user_text})

        # build request
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(
                message={
                    "role": "user",
                    "messageId": uuid4().hex,
                    "parts": parts
                }
            )
        )

        # send message
        response = await client.send_message(request)
        resp_dict = response.model_dump(mode="json", exclude_none=True)
        logger.info(f"[call_downstream] Received response from agent")

        # extract text part (your agents return JSON in a text block)
        result = resp_dict.get("result", {})
        out_parts = result.get("parts", [])
        text = None
        for p in out_parts:
            if p.get("kind") == "text" or p.get("type") == "text":
                text = p.get("text", "").strip()
                break

        if text is None:
            logger.warning(f"[call_downstream] No text part found in response")
            return {"raw_response": resp_dict}

        try:
            parsed = json.loads(text)
            logger.info(f"[call_downstream] Successfully parsed JSON response")
            return parsed
        except Exception as e:
            logger.warning(f"[call_downstream] Failed to parse JSON: {e}, returning raw text")
            return {"raw_text": text}



class OrchestratorExecutor(AgentExecutor):
    def __init__(self):
        super().__init__()
        self.planner = PlannerLLM()
        self.synth = SynthesizerLLM()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_task = (get_message_text(context.message) or "").strip()
        data_parts = get_data_parts(context.message.parts) or []

        # detect approval pass-through from user (same as before)
        approved = any(bool(dp.get("approved", False)) for dp in data_parts)

        logger.info(f"[Orchestrator] user_task={user_task!r}, approved={approved}")

        # 1) PLAN
        raw_plan = await self.planner.plan(user_task)
        plan = validate_plan(raw_plan, ALLOWED_AGENTS)
        logger.info(f"[Orchestrator] plan={plan}")

        # 2) EXECUTE SUBTASKS SEQUENTIALLY
        state: Dict[str, Any] = {}
        trace = []

        for st in plan["subtasks"]:
            agent = st["agent"]
            task_template = st["task"]

            # simple variable substitution from state
            task_filled = task_template.format(**state)

            agent_url = TERMINAL_URL if agent == "terminal" else WEB_URL
            downstream_res = await call_downstream(agent_url, task_filled, data_parts=data_parts)

            trace.append({
                "id": st["id"],
                "agent": agent,
                "task": task_filled,
                "result": downstream_res
            })

            # 2.b) Approval stop condition
            if (not approved) and downstream_res.get("reason") == "approval_required":
                payload = {
                    "ok": False,
                    "reason": "approval_required",
                    "plan": plan,
                    "pending_subtask": st,
                    "pending_agent_response": downstream_res,
                    "message": "One subtask requires approval. Resend the SAME request with approved=true."
                }
                await event_queue.enqueue_event(
                    new_agent_text_message(json.dumps(payload, indent=2))
                )
                return

            # store output for later steps
            # Extract useful data from downstream response, not the entire JSON
            key = st["output_key"]
            
            # Extract the actual result from the response
            if isinstance(downstream_res, dict):
                # Web agent format: extract final_result from execution
                if "execution" in downstream_res and isinstance(downstream_res["execution"], dict):
                    final_result = downstream_res["execution"].get("final_result")
                    if final_result:
                        state[key] = final_result
                    else:
                        # Fallback: use the execution dict as JSON string
                        state[key] = json.dumps(downstream_res["execution"], indent=2)
                # Terminal agent format: might have final_answer or text
                elif "final_answer" in downstream_res:
                    state[key] = downstream_res["final_answer"]
                elif "text" in downstream_res:
                    state[key] = downstream_res["text"]
                # If it's a simple dict with a result key
                elif "result" in downstream_res:
                    state[key] = downstream_res["result"]
                else:
                    # Last resort: store a summary string
                    state[key] = json.dumps(downstream_res, indent=2)
            else:
                # Not a dict, store as string
                state[key] = str(downstream_res)
            
            logger.info(f"[Orchestrator] Stored state[{key}] = {str(state[key])[:200]}...")

        # 3) SYNTHESIZE FINAL ANSWER
        final_answer = await self.synth.synthesize(plan["goal"], state)

        payload = {
            "ok": True,
            "plan": plan,
            "execution_trace": trace,
            "state": state,
            "final_answer": final_answer
        }

        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps(payload, indent=2))
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(
            new_agent_text_message("cancel not supported for OrchestratorExecutor")
        )