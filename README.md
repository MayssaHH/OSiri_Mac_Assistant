# Web Agent

The Web Agent is a specialized agent for web-related tasks in the OSiri multi-agent system. It provides capabilities for web search, URL scraping, and browser history access.

## Architecture

The Web Agent follows a two-layer architecture:

### 1. MCP Layer (`web_mcp/`)
Exposes tools via the Model Context Protocol (MCP):
- **Tools**: `search_web`, `scrape_url`, `get_browser_history`
- **Agents**: Planner and Executor agents using Microsoft Agent Framework (MAF)
- **Protocol**: MCP over stdio (subprocess communication)

### 2. A2A Layer (`web_a2a/`)
Exposes the complete agent via Agent-to-Agent (A2A) protocol:
- **Server**: HTTP server on port 9998
- **Protocol**: A2A over HTTP (JSONRPC)
- **Purpose**: Remote access for orchestrator and other agents

## Features

### 🔍 Web Search
- Search the internet using Tavily API
- Returns parsed, agent-optimized results
- **Tool**: `search_web(query: str)`

### 📄 URL Scraping
- Extract clean text content from any URL
- Uses Trafilatura for content extraction
- **Tool**: `scrape_url(url: str)`

### 🌐 Browser History
- Access Safari and Chrome browsing history
- Filter by time range, count, and domain
- **Tool**: `get_browser_history(hours: int, count: int, domain: str)`

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your_openai_key_here
TAVILY_API_KEY=your_tavily_key_here
```

### 3. Run the A2A Server

```bash
python -m web_a2a.web_a2a_server
```

The server will start on `http://127.0.0.1:9998/`

## Usage

### From the Orchestrator (A2A)

```python
from a2a.client import ClientFactory

# Connect to the Web Agent
client = await ClientFactory.connect("http://127.0.0.1:9998/")

# Send a task
from a2a.types import Message, Part, Role, TextPart
import uuid

message = Message(
    role=Role.user,
    parts=[Part(root=TextPart(text="What GitHub repos did I visit today?"))],
    message_id=str(uuid.uuid4()),
)

# Get response
async for event in client.send_message(message):
    if hasattr(event, 'parts') and event.parts:
        for part in event.parts:
            if hasattr(part.root, 'text'):
                print(part.root.text)
```

### Direct Tool Usage (MCP)

```python
from web_mcp.web_client import search_web, scrape_url, get_browser_history

# Search the web
result = await search_web("latest macOS version")

# Scrape a URL
content = await scrape_url("https://example.com")

# Get browser history
history = await get_browser_history(hours=24, count=10, domain="github.com")
```

### Using the MAF Agents

```python
from web_mcp.web_agent import build_agent, run_task_with_plan

# Single agent (direct tool calling)
agent = build_agent()
response = await agent.run("What GitHub repos did I visit today?")
print(response.text)

# Plan-Execute pattern (planner + executor)
await run_task_with_plan("Summarize the last 3 papers I read on arXiv")
```

## File Structure

```
OSiri_Mac_Assistant/
├── .env                        # Environment variables
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── web_mcp/                    # MCP Layer
│   ├── __init__.py
│   ├── web_mcp_server.py      # MCP server exposing tools
│   ├── web_client.py          # Python wrapper for MCP tools
│   ├── web_agent.py           # MAF agents (planner + executor)
│   └── prompt.py              # System prompts for agents
│
└── web_a2a/                    # A2A Layer
    ├── __init__.py
    ├── web_a2a_server.py      # A2A HTTP server
    └── web_a2a_executer.py    # Request handler & orchestration
```

## Agent Card

The Web Agent exposes the following skill via A2A:

**Skill ID**: `web_assistant`

**Examples**:
- "Search for the latest macOS version"
- "Summarize the article at https://example.com"
- "What GitHub repos did I visit today?"
- "Find Python tutorials and summarize the first result"

## Technical Details

### Technologies
- **Agent Framework**: Microsoft Agent Framework (MAF)
- **LLM**: OpenAI GPT-4o
- **MCP**: Model Context Protocol (stdio transport)
- **A2A**: Agent-to-Agent protocol (HTTP/JSONRPC)
- **Search API**: Tavily
- **Content Extraction**: Trafilatura
- **Browser History**: SQLite (Safari/Chrome)

### Ports
- **A2A Server**: 9998
- **MCP Server**: stdio (subprocess, no port)

### Dependencies
See `requirements.txt` for full list:
- `agent-framework` - Microsoft Agent Framework
- `tavily-python` - Tavily search API
- `trafilatura` - Content extraction
- `openai` - OpenAI API client
- `mcp` - Model Context Protocol
- `a2a` - Agent-to-Agent protocol
- `uvicorn` - ASGI server
- `fastapi` - Web framework

## Troubleshooting

### Tavily API Issues
If you get a 403 error from Tavily:
1. Verify your API key is correct in `.env`
2. Check your Tavily account is verified
3. Ensure you haven't exceeded rate limits
4. Try generating a new API key from the Tavily dashboard

### Browser History Not Found
- **Safari**: Ensure you've used Safari recently
- **Chrome**: Check if you're using a non-default profile
  - The agent checks: Default, Profile 1, Profile 2
  - For other profiles, update `web_mcp_server.py`

### MCP Connection Issues
- The MCP server runs as a subprocess automatically
- If you see connection errors, check Python path in `web_client.py`
- Ensure all dependencies are installed in the active venv

### A2A Timeout
- Default timeout is 120 seconds
- For long-running tasks, increase timeout in client:
  ```python
  httpx_client = httpx.AsyncClient(timeout=300.0)
  config = ClientConfig(httpx_client=httpx_client)
  client = await ClientFactory.connect(base_url, client_config=config)
  ```

## Development

### Running Tests
All test files have been removed from the production codebase. For testing during development:

1. **Test MCP tools directly**:
   ```python
   from web_mcp.web_client import get_browser_history
   result = await get_browser_history(hours=24, count=10)
   print(result)
   ```

2. **Test MAF agents**:
   ```python
   from web_mcp.web_agent import build_agent
   agent = build_agent()
   response = await agent.run("Your query here")
   print(response.text)
   ```

3. **Test A2A server**:
   - Start server: `python -m web_a2a.web_a2a_server`
   - Use A2A client to send requests (see Usage section)

## License

Part of the OSiri Mac Assistant project.

