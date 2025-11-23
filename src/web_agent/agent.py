import os
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from .tools import search_web, scrape_url, get_browser_history

def create_web_agent() -> ChatAgent:
    """
    Creates and configures the OSiri Web Agent using the Microsoft Agent Framework.
    """
    # 1. Define the Chat Client
    client = OpenAIChatClient(
        model_id="gpt-4o",
        api_key=os.environ.get("OPENAI_API_KEY")
    )

    # 2. Define the Agent
    agent = ChatAgent(
        name="OSiri_Web_Agent",
        chat_client=client,
        instructions=(
            "You are the Web Specialist for OSiri, a macOS assistant. "
            "Your goal is to fetch accurate information from the internet and help users "
            "access their browsing history. "
            "\n\n"
            "GUIDELINES:\n"
            "1. Use 'search_web' for general queries (e.g. 'What is the weather?').\n"
            "2. Use 'scrape_url' ONLY when the user provides a specific link to read.\n"
            "3. Use 'get_browser_history' when the user asks about:\n"
            "   - 'What did I read/visit today/yesterday?'\n"
            "   - 'Show me my recent tabs/history'\n"
            "   - 'Find that website I looked at...'\n"
            "   - 'What GitHub repos did I visit?'\n"
            "   You can filter by time (hours parameter) and domain.\n"
            "4. Always cite your sources at the end of your response.\n"
            "5. Be concise but professional."
        ),
        tools=[search_web, scrape_url, get_browser_history]
    )

    return agent
