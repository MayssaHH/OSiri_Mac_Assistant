import os
import json
import logging
from datetime import datetime
from typing import Callable, Awaitable
from .terminal_client import open_shell, run_command, close_shell, list_shells, get_cwd, terminal_mcp
from agent_framework import AgentRunContext, FunctionInvocationContext # type: ignore
from agent_framework.openai import OpenAIChatClient   # type: ignore
from .prompt import get_system_prompt, get_planner_prompt, get_execution_prompt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("terminal_assistant")
logger.setLevel(logging.INFO)

# I want to log the tool calls 
if not logger.handlers:
    ch = logging.StreamHandler()
    fh = logging.FileHandler("tool_calls.log", encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    ch.setFormatter(fmt)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)

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

def build_agent():
    client = OpenAIChatClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_id="gpt-4o-mini"
    )

    agent = client.create_agent(
        name="TerminalAssistant",
        description="An agent that executes terminal commands through a local MCP server.",
        instructions=get_system_prompt(),
        tools=[open_shell, run_command, close_shell, list_shells, get_cwd],
        middleware=[agent_run_logger, function_call_logger],
    )
    return agent

def build_planner_agent(client):
    return client.create_agent(
        name="TerminalAssistantPlanner",
        instructions=get_planner_prompt(),
        middleware=[agent_run_logger],  
    )

def build_executor_agent(client):
    return client.create_agent(
        name="TerminalAssistantExecutor",
        instructions=get_execution_prompt(),
        tools=[open_shell, run_command, close_shell, list_shells, get_cwd],
        middleware=[agent_run_logger, function_call_logger],
    )

async def run_task_with_plan(task: str, auto_approve: bool = False):
    client = OpenAIChatClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_id="gpt-4o-mini"
    )

    planner = build_planner_agent(client)
    executor = build_executor_agent(client)

    # 1) PLAN
    plan_res = await planner.run(task)
    plan_text = plan_res.text.strip()

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

    # 3) EXECUTE + VERIFY (model will call tools)
    exec_prompt = f"""
    User goal:
    {task}

    JSON plan:
    {json.dumps(plan_json, indent=2)}
    """
    exec_res = await executor.run(exec_prompt)
    print("\n--- EXECUTION REPORT ---")
    print(exec_res.text)

    await terminal_mcp.close()
