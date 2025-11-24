"""
Web MCP Client
Wraps the MCP server tools as Python functions for agents to use.
"""
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager
import json

_approved_mode = False

def set_approved_mode(approved: bool):
    """Set global approval mode for risky operations"""
    global _approved_mode
    _approved_mode = approved

def get_approved_mode() -> bool:
    """Get current approval mode"""
    return _approved_mode

@asynccontextmanager
async def get_web_mcp():
    """Create a new MCP client session"""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "web_mcp.web_mcp_server"],
        env=os.environ.copy()  # Pass environment variables to subprocess
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session

# ============================================================================
# Wrapped Tool Functions (for MAF agents)
# ============================================================================

async def search_web(query: str) -> dict:
    """
    Search the web using Tavily.
    
    Args:
        query: Search query string
        
    Returns:
        dict with search results or error
    """
    async with get_web_mcp() as session:
        result = await session.call_tool("search_web", arguments={"query": query})
        if result.content:
            text = result.content[0].text
            return json.loads(text) if isinstance(text, str) else text
        return {"ok": False, "error": "No response"}

async def scrape_url(url: str) -> dict:
    """
    Scrape text content from a URL.
    
    Args:
        url: The URL to scrape
        
    Returns:
        dict with scraped text or error
    """
    async with get_web_mcp() as session:
        result = await session.call_tool("scrape_url", arguments={"url": url})
        if result.content:
            text = result.content[0].text
            return json.loads(text) if isinstance(text, str) else text
        return {"ok": False, "error": "No response"}

async def get_browser_history(hours: int = 24, count: int = 10, domain: str = None) -> dict:
    """
    Get browser history.
    
    Args:
        hours: Look back this many hours
        count: Max number of results
        domain: Optional domain filter
        
    Returns:
        dict with browser history or error
    """
    args = {"hours": hours, "count": count}
    if domain:
        args["domain"] = domain
    
    async with get_web_mcp() as session:
        result = await session.call_tool("get_browser_history", arguments=args)
        if result.content:
            text = result.content[0].text
            return json.loads(text) if isinstance(text, str) else text
        return {"ok": False, "error": "No response"}

