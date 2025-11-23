import os
import logging
import uvicorn
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from orchestrator_a2a_executer import OrchestratorExecutor

load_dotenv()

# Setup logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("orchestrator_tool_calls.log", encoding="utf-8")
    ]
)


def build_agent_card(base_url: str) -> AgentCard:
    skill = AgentSkill(
        id="orchestrate",
        name="Mesh Orchestrator",
        description="Routes user tasks to specialist A2A agents (terminal, web).",
        tags=["orchestrator", "routing", "mesh"],
        examples=[
            "Create a folder and a hello.py file on Desktop",
            "Search the web for the latest paper about KAN kernels"
        ],
    )

    return AgentCard(
        name="Osiri Orchestrator",
        description="Top-level A2A orchestrator that delegates tasks to other agents.",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        supports_authenticated_extended_card=False,
    )


def main():
    host = os.getenv("A2A_HOST")
    port = int(os.getenv("A2A_PORT"))
    base_url = os.getenv("A2A_BASE_URL")

    agent_card = build_agent_card(base_url)

    handler = DefaultRequestHandler(
        agent_executor=OrchestratorExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    uvicorn.run(app.build(), host=host, port=port)


if __name__ == "__main__":
    main()
