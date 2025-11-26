"""
MAF Agent (Slack + Outlook)
Provides single-agent and plan-execute patterns
"""
import os
import json
import logging
from datetime import datetime
from typing import Callable, Awaitable
from .maf_client import send_slack_message, read_slack_messages, send_outlook_email, read_outlook_emails
from agent_framework import AgentRunContext, FunctionInvocationContext
from agent_framework.openai import OpenAIChatClient
from .prompt import get_system_prompt, get_planner_prompt, get_execution_prompt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("maf_assistant")
logger.setLevel(logging.INFO)

# Setup logging
if not logger.handlers:
    ch = logging.StreamHandler()
    fh = logging.FileHandler("maf_tool_calls.log", encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    ch.setFormatter(fmt)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)

# ============================================================================
# Middleware for logging
# ============================================================================

async def agent_run_logger(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    logger.info(f"[AgentRun] START messages={len(context.messages)}")
    await next(context)
    logger.info(f"[AgentRun] END messages={len(context.messages)}")


async def function_call_logger(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
):
    fn = context.function.name
    args = context.arguments

    t0 = datetime.now()
    logger.info(f"[ToolCall] -> {fn} args={args}")

    result = await next(context)

    dt = (datetime.now() - t0).total_seconds()
    logger.info(f"[ToolCall] <- {fn} result={result} ({dt:.3f}s)")

    return result

# ============================================================================
# Agent Builders
# ============================================================================

def build_agent():
    """
    Build a single all-in-one MAF agent.
    Use this for simple interactive tasks.
    """
    client = OpenAIChatClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_id="gpt-4o"
    )

    agent = client.create_agent(
        name="CommunicationAssistant",
        description="An agent that handles Slack and Outlook communications.",
        instructions=get_system_prompt(),
        tools=[send_slack_message, read_slack_messages, send_outlook_email, read_outlook_emails],
        middleware=[agent_run_logger, function_call_logger],
    )
    return agent


def build_planner_agent(client):
    """
    Build a planner agent (no tools).
    Creates JSON execution plans.
    """
    return client.create_agent(
        name="CommunicationTaskPlanner",
        instructions=get_planner_prompt(),
        middleware=[agent_run_logger],
    )


def build_executor_agent(client):
    """
    Build an executor agent (with tools).
    Executes JSON plans step-by-step.
    """
    return client.create_agent(
        name="CommunicationTaskExecutor",
        instructions=get_execution_prompt(),
        tools=[send_slack_message, read_slack_messages, send_outlook_email, read_outlook_emails],
        middleware=[agent_run_logger, function_call_logger],
    )


async def run_task_with_plan(task: str, auto_approve: bool = False):
    """
    Execute a task using the plan-execute pattern.
    
    Args:
        task: User's task description
        auto_approve: If True, skip manual approval
    """
    client = OpenAIChatClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_id="gpt-4o"
    )

    planner = build_planner_agent(client)
    executor = build_executor_agent(client)

    # 1) PLAN
    plan_res = await planner.run(task)
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
        plan_json = json.loads(plan_text)
    except Exception:
        raise ValueError(f"Planner did not return valid JSON:\n{plan_text}")

    print("\n--- PLAN ---")
    print(json.dumps(plan_json, indent=2))

    # 2) APPROVE
    if not auto_approve:
        ans = input("\nApprove plan? (y/n): ").strip().lower()
        if ans != "y":
            print("Plan rejected. Exiting.")
            return

    # 3) EXECUTE
    exec_prompt = f"""
    User goal:
    {task}

    JSON plan:
    {json.dumps(plan_json, indent=2)}
    """
    exec_res = await executor.run(exec_prompt)
    print("\n--- EXECUTION REPORT ---")
    print(exec_res.text)

