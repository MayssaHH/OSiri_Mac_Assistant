import uvicorn
import sys
from pathlib import Path

# Ensure we can import from sibling directories if needed
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from maf_executor import MafAgentExecutor

def build_agent_card(base_url: str) -> AgentCard:
    maf_skill = AgentSkill(
        id="maf_assistant",
        name="MAF Assistant",
        description="Manages Slack and Email communications.",
        tags=["slack", "email", "communication"],
        examples=[
            "Check my unread emails",
            "Send a slack message to #general saying hello",
        ],
    )

    return AgentCard(
        name="MAF A2A Server",
        description="Agent capable of Slack and Email operations via MCP.",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[maf_skill],
        supports_authenticated_extended_card=False,
    )

def main():
    host = "127.0.0.1"
    port = 9000 # Different port from terminal agent (usually 9999)
    base_url = f"http://{host}:{port}/"

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

