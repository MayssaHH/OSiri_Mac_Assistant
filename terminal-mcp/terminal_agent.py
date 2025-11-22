import os
from terminal_client import open_shell, run_command, close_shell, list_shells, get_cwd
from agent_framework.openai import OpenAIChatClient  # type: ignore
from prompt import get_system_prompt
from dotenv import load_dotenv

load_dotenv()

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
    )
    return agent


