import os
import sys
import json
from pathlib import Path
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.message import get_message_text, new_agent_text_message
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Import our MCP client tools
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from maf_mcp.maf_client import read_slack, send_slack, read_email, send_email, maf_mcp

load_dotenv()

class MafAgentExecutor(AgentExecutor):
    def __init__(self):
        super().__init__()
        client = OpenAIChatClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_id="gpt-4o"
        )
        # Create the agent with our tools
        self.agent = client.create_agent(
            name="MafAssistant",
            instructions=(
                "You are a helpful assistant capable of reading/sending Slack messages and Emails using your tools. "
                "Always verify the tool output and summarize it clearly for the user."
            ),
            tools=[read_slack, send_slack, read_email, send_email],
        )

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_text = get_message_text(context.message)
        
        # Run the agent
        # Note: ensure agent.run returns an object with .text
        try:
            result = await self.agent.run(task_text)
            response_text = result.text
        except Exception as e:
            response_text = f"Error executing agent: {str(e)}"
        
        # Return the response
        await event_queue.enqueue_event(
            new_agent_text_message(response_text)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass

