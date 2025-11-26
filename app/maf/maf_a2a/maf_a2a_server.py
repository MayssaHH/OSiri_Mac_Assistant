"""
MAF A2A Server
Exposes the MAF Agent via Agent-to-Agent (A2A) protocol over HTTP.
"""
import os
import sys
import uvicorn
from pathlib import Path

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from .maf_a2a_executer import MAFAgentExecutor
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

def build_agent_card(base_url: str) -> AgentCard:
    """Build the agent card describing MAF agent capabilities"""
    maf_skill = AgentSkill(
        id="maf_assistant",
        name="Communication Assistant",
        description=(
            "Handles Slack messages and Outlook emails. "
            "Uses internal planner+executor to solve multi-step communication tasks."
        ),
        tags=["slack", "outlook", "email", "chat"],
        examples=[
            "Check my unread emails",
            "Send a message to #general saying I'm online",
            "Summarize the last 5 emails from Boss and send a Slack summary to #team",
        ],
    )

    return AgentCard(
        name="MAF A2A Server",
        description="Remote communication agent for Slack and Outlook, using internal planner+executor.",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[maf_skill],
        supports_authenticated_extended_card=False,
    )


def main():
    host = os.getenv("A2A_HOST", "127.0.0.1")
    # Fallback to 8003 if not set
    port = int(os.getenv("MAF_AGENT_PORT", "8003"))
    base_url = os.getenv("MAF_AGENT_URL", f"http://{host}:{port}")

    agent_card = build_agent_card(base_url)

    request_handler = DefaultRequestHandler(
        agent_executor=MAFAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    print(f"📧 MAF A2A Server starting on {base_url}")
    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()

