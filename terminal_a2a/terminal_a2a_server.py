import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from terminal_a2a_executer import TerminalAgentExecutor


def build_agent_card(base_url: str) -> AgentCard:
    terminal_skill = AgentSkill(
        id="terminal_assistant",
        name="Terminal Assistant",
        description=(
            "Plans and executes safe terminal tasks on the host machine. "
            "Uses internal planner+executor to solve multi-step terminal tasks end-to-end locally."
        ),
        tags=["terminal", "shell"],
        examples=[
            "Create a folder on my Desktop called test and add hello.py",
            "List files in ~/Downloads and show me the biggest ones",
            "Make a virtualenv and install numpy (approved=true)",
        ],
    )

    return AgentCard(
        name="Terminal A2A Server",
        description="Remote terminal agent executing safe terminal tasks on the host machine, using internal planner+executor to solve multi-step terminal tasks end-to-end locally.",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[terminal_skill],
        supports_authenticated_extended_card=False,
    )


def main():
    host = os.getenv("A2A_HOST")
    port = int(os.getenv("TERMINAL_AGENT_PORT"))
    base_url = os.getenv("TERMINAL_AGENT_URL")

    agent_card = build_agent_card(base_url)

    request_handler = DefaultRequestHandler(
        agent_executor=TerminalAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()
