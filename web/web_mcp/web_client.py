"""
Web MCP Client
Wraps the MCP server tools as Python functions for agents to use.
Includes automatic retry with checkpoint tracking.
"""
import os
import sys
import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager
import json
from typing import Dict, Any, Callable, Optional

# Add parent directories to path for common imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.checkpoint import CheckpointManager

logger = logging.getLogger("web-mcp-client")

_approved_mode = False

# Global checkpoint manager for retry tracking
checkpoint_manager = CheckpointManager(default_max_retries=3)

# Current task ID for checkpoint tracking (set by executor)
_current_task_id: Optional[str] = None


def set_approved_mode(approved: bool):
    """Set global approval mode for risky operations"""
    global _approved_mode
    _approved_mode = approved


def get_approved_mode() -> bool:
    """Get current approval mode"""
    return _approved_mode


def set_current_task_id(task_id: Optional[str]):
    """Set the current task ID for checkpoint tracking"""
    global _current_task_id
    _current_task_id = task_id


def get_current_task_id() -> Optional[str]:
    """Get the current task ID"""
    return _current_task_id


def clear_task_checkpoints(task_id: str):
    """Clear all checkpoints for a completed task"""
    checkpoint_manager.clear_task(task_id)

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


async def _call_tool_with_retry(
    tool_name: str,
    arguments: Dict[str, Any],
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> dict:
    """
    Call an MCP tool with automatic retry on failure.
    
    Records checkpoints for tracking and retries automatically if the call fails.
    
    Args:
        tool_name: Name of the MCP tool to call
        arguments: Arguments to pass to the tool
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (multiplied by attempt number)
        
    Returns:
        Tool result dict
    """
    task_id = get_current_task_id() or "unknown"
    last_result = {"ok": False, "error": "No attempts made"}
    
    for attempt in range(max_retries + 1):
        try:
            async with get_web_mcp() as session:
                result = await session.call_tool(tool_name, arguments=arguments)
                
                if result.content:
                    text = result.content[0].text
                    parsed = json.loads(text) if isinstance(text, str) else text
                else:
                    parsed = {"ok": False, "error": "No response from tool"}
                
                # Record checkpoint
                cp = checkpoint_manager.record_web(
                    task_id=task_id,
                    tool_name=tool_name,
                    tool_args=arguments,
                    result=parsed,
                    max_retries=max_retries,
                )
                cp.retry_count = attempt
                
                # Check if successful
                if parsed.get("ok", False):
                    if attempt > 0:
                        logger.info(f"[{tool_name}] Succeeded on retry {attempt}")
                    return parsed
                
                last_result = parsed
                
                # Check if we should retry
                if attempt < max_retries:
                    delay = retry_delay * (attempt + 1)
                    logger.warning(
                        f"[{tool_name}] Failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay}s: {parsed.get('error', 'Unknown error')}"
                    )
                    await asyncio.sleep(delay)
                    
        except Exception as e:
            last_result = {"ok": False, "error": f"Exception: {repr(e)}"}
            
            if attempt < max_retries:
                delay = retry_delay * (attempt + 1)
                logger.warning(
                    f"[{tool_name}] Exception (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {delay}s: {repr(e)}"
                )
                await asyncio.sleep(delay)
    
    logger.error(f"[{tool_name}] All {max_retries + 1} attempts failed")
    return last_result

# ============================================================================
# Wrapped Tool Functions (for MAF agents)
# All functions use automatic retry with checkpoint tracking
# ============================================================================

async def search_web(query: str, max_retries: int = 3) -> dict:
    """
    Search the web using Tavily.
    
    Automatically retries on failure up to max_retries times.
    
    Args:
        query: Search query string
        max_retries: Maximum retry attempts (default: 3)
        
    Returns:
        dict with search results or error
    """
    return await _call_tool_with_retry(
        tool_name="search_web",
        arguments={"query": query},
        max_retries=max_retries,
    )


async def scrape_url(url: str, max_retries: int = 3) -> dict:
    """
    Scrape text content from a URL.
    
    Automatically retries on failure up to max_retries times.
    
    Args:
        url: The URL to scrape
        max_retries: Maximum retry attempts (default: 3)
        
    Returns:
        dict with scraped text or error
    """
    return await _call_tool_with_retry(
        tool_name="scrape_url",
        arguments={"url": url},
        max_retries=max_retries,
    )


async def get_browser_history(
    hours: int = 24, 
    count: int = 10, 
    domain: str = None,
    max_retries: int = 3,
) -> dict:
    """
    Get browser history.
    
    Automatically retries on failure up to max_retries times.
    
    Args:
        hours: Look back this many hours
        count: Max number of results
        domain: Optional domain filter
        max_retries: Maximum retry attempts (default: 3)
        
    Returns:
        dict with browser history or error
    """
    args = {"hours": hours, "count": count}
    if domain:
        args["domain"] = domain
    
    return await _call_tool_with_retry(
        tool_name="get_browser_history",
        arguments=args,
        max_retries=max_retries,
    )


async def filter_browser_history(
    history: list, 
    intent: str, 
    top_k: int = 1,
    max_retries: int = 3,
) -> dict:
    """
    LLM-based filter over history entries.
    
    Automatically retries on failure up to max_retries times.
    
    Args:
        history: List of browser history entries
        intent: User intent for filtering
        top_k: Number of top matches to return
        max_retries: Maximum retry attempts (default: 3)
        
    Returns:
        dict with filtered results or error
    """
    return await _call_tool_with_retry(
        tool_name="filter_browser_history",
        arguments={"history": history, "intent": intent, "top_k": top_k},
        max_retries=max_retries,
    )
