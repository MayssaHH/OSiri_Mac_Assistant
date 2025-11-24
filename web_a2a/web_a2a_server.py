"""
Web A2A Server
Exposes the Web Agent via Agent-to-Agent (A2A) protocol over HTTP.
"""
import os
import sys
import uvicorn
from pathlib import Path

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from .web_a2a_executer import WebAgentExecutor
from dotenv import load_dotenv


root_dir = Path(__file__).parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

def build_agent_card(base_url: str) -> AgentCard:
    """Build the agent card describing web agent capabilities"""
    web_skill = AgentSkill(
        id="web_assistant",
        name="Web Assistant",
        description=(
            "Performs web searches, scrapes URLs, and accesses browser history."
            "Uses internal planner+executor to solve multi-step web tasks end-to-end."
        ),
        tags=["web", "search", "scraping", "browser"],
        examples=[
            "Search for the latest macOS version",
            "Summarize the article at https://example.com",
            "What GitHub repos did I visit today?",
            "Find Python tutorials and summarize the first result",
        ],
    )

    return AgentCard(
        name="Web A2A Server",
        description="Remote web agent exposing search, scraping, and browser history, using internal planner+executor to solve multi-step web tasks end-to-end.",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[web_skill],
        supports_authenticated_extended_card=False,
    )


def main():
    host = os.getenv("A2A_HOST")
    port = int(os.getenv("WEB_AGENT_PORT"))
    base_url = os.getenv("WEB_AGENT_URL")

    agent_card = build_agent_card(base_url)

    request_handler = DefaultRequestHandler(
        agent_executor=WebAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    print(f"🌐 Web A2A Server starting on {base_url}")
    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()

