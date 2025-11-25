import uvicorn
import sys
from pathlib import Path
import os

# Ensure we can import from sibling directories if needed
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from .maf_executor import MafAgentExecutor

def build_agent_card(base_url: str) -> AgentCard:
    """
    Application Agent (Slack + Gmail) A2A card.
    This is what other agents/orchestrators will discover.
    """
    app_skill = AgentSkill(
        id="app_assistant",
        name="Application Assistant",
        description=(
            "Agent that can manage Slack and Email (Gmail) workflows using MCP-backed tools. "
            "It can read emails, summarize them, and post to Slack channels, as well as send emails "
            "based on Slack information or user instructions."
        ),
        examples=[
            "Read my last 3 unread emails and post a one-line summary of each to #general.",
            "Send an email to my manager summarizing today’s Slack standup.",
            "List my Slack channels and post a status update in #random.",
        ],
        tags=["slack", "email", "applications"],
    )

    return AgentCard(
        name="Application A2A Server",
        description="Unified application agent for Slack and Gmail operations.",
        url=base_url,
        version="0.1.0",
        protocolVersion="0.3.0",
        preferredTransport="JSONRPC",
        capabilities=AgentCapabilities(streaming=False),
        skills=[app_skill],
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        supportsAuthenticatedExtendedCard=False,
    )


def main():
    host = os.getenv("A2A_HOST")
    port = int(os.getenv("APP_AGENT_PORT"))
    base_url = os.getenv("APP_AGENT_URL")

    agent_card = build_agent_card(base_url)

    request_handler = DefaultRequestHandler(
        agent_executor=MafAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    print(f"Starting MAF A2A Server at {base_url}")
    uvicorn.run(server.build(), host=host, port=port)

if __name__ == "__main__":
    main()

