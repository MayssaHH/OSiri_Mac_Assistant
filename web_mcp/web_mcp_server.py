"""
Web MCP Server
Exposes web-related tools via Model Context Protocol (MCP).
Tools: search_web, scrape_url, get_browser_history
"""
import os
import sqlite3
import shutil
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient
import trafilatura

mcp = FastMCP(name="Web MCP Server")

# ============================================================================
# Tool 1: Web Search (Tavily)
# ============================================================================

@mcp.tool()
def search_web(query: str) -> dict:
    """
    Searches the web for information using Tavily API.
    
    Args:
        query: The search query string
        
    Returns:
        dict with 'ok', 'results' (list of {title, url, content}), or 'error'
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"ok": False, "error": "TAVILY_API_KEY not set"}
    
    try:
        tavily = TavilyClient(api_key)
        response = tavily.search(query=query, max_results=3, search_depth="advanced")
        
        results = response.get('results', [])
        if not results:
            return {"ok": True, "results": [], "message": "No results found"}
        
        # Format results
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get('title', 'No Title'),
                "url": r.get('url', ''),
                "content": r.get('content', '')
            })
        
        return {"ok": True, "results": formatted}
    
    except Exception as e:
        return {"ok": False, "error": f"Search failed: {repr(e)}"}


# ============================================================================
# Tool 2: URL Scraping (Trafilatura)
# ============================================================================

@mcp.tool()
def scrape_url(url: str) -> dict:
    """
    Extracts clean text content from a specific URL.
    
    Args:
        url: The URL to scrape
        
    Returns:
        dict with 'ok', 'text', 'url', or 'error'
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"ok": False, "error": "Could not fetch URL (404, blocked, or invalid)"}
        
        text = trafilatura.extract(downloaded)
        if not text:
            return {"ok": False, "error": "No text content found on page"}
        
        return {"ok": True, "url": url, "text": text}
    
    except Exception as e:
        return {"ok": False, "error": f"Scrape failed: {repr(e)}"}


# ============================================================================
# Tool 3: Browser History (Safari/Chrome)
# ============================================================================

@mcp.tool()
def get_browser_history(hours: int = 24, count: int = 10, domain: str = None) -> dict:
    """
    Retrieves recent browser history from Safari or Chrome.
    
    Args:
        hours: Look back this many hours (default: 24)
        count: Maximum number of results (default: 10)
        domain: Optional domain filter (e.g., "github.com")
        
    Returns:
        dict with 'ok', 'browser', 'results' (list of {timestamp, title, url}), or 'error'
    """
    # Detect browser
    safari_db = os.path.expanduser("~/Library/Safari/History.db")
    chrome_base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    
    db_path = None
    browser = None
    
    # Try Chrome first (check multiple profiles)
    chrome_profiles = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4"]
    chrome_db = None
    
    for profile in chrome_profiles:
        potential_db = os.path.join(chrome_base, profile, "History")
        if os.path.exists(potential_db):
            chrome_db = potential_db
            break
    
    if chrome_db:
        try:
            # Chrome locks the DB, so copy it first
            shutil.copy(chrome_db, "/tmp/History_copy")
            db_path = "/tmp/History_copy"
            browser = "chrome"
        except Exception as e:
            return {"ok": False, "error": f"Could not access Chrome history: {e}"}
    elif os.path.exists(safari_db):
        db_path = safari_db
        browser = "safari"
    else:
        return {"ok": False, "error": "No supported browser history found (Safari or Chrome)"}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Calculate timestamp cutoff
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        if browser == "safari":
            # Safari uses Cocoa timestamp (seconds since 2001-01-01)
            cocoa_epoch = datetime(2001, 1, 1)
            timestamp = (cutoff_time - cocoa_epoch).total_seconds()
            
            query = """
                SELECT h.url, v.title, v.visit_time
                FROM history_items h
                JOIN history_visits v ON h.id = v.history_item
                WHERE v.visit_time > ?
            """
            params = [timestamp]
            
            if domain:
                query += " AND h.url LIKE ?"
                params.append(f"%{domain}%")
            
            query += " ORDER BY v.visit_time DESC LIMIT ?"
            params.append(count)
            
            cursor.execute(query, params)
        
        elif browser == "chrome":
            # Chrome uses microseconds since 1601-01-01
            chrome_epoch = datetime(1601, 1, 1)
            timestamp = int((cutoff_time - chrome_epoch).total_seconds() * 1000000)
            
            query = """
                SELECT u.url, u.title, v.visit_time
                FROM urls u
                JOIN visits v ON u.id = v.url
                WHERE v.visit_time > ?
            """
            params = [timestamp]
            
            if domain:
                query += " AND u.url LIKE ?"
                params.append(f"%{domain}%")
            
            query += " ORDER BY v.visit_time DESC LIMIT ?"
            params.append(count)
            
            cursor.execute(query, params)
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            filter_msg = f" matching domain '{domain}'" if domain else ""
            return {
                "ok": True,
                "browser": browser,
                "results": [],
                "message": f"No history found in the last {hours} hours{filter_msg}"
            }
        
        # Format output
        formatted = []
        for url, title, timestamp in results:
            title = title or "No Title"
            # Convert timestamp to human-readable format
            if browser == "safari":
                visit_time = datetime(2001, 1, 1) + timedelta(seconds=timestamp)
            else:  # chrome
                visit_time = datetime(1601, 1, 1) + timedelta(microseconds=timestamp)
            
            formatted.append({
                "timestamp": visit_time.strftime("%Y-%m-%d %H:%M:%S"),
                "title": title,
                "url": url
            })
        
        return {"ok": True, "browser": browser, "results": formatted}
    
    except Exception as e:
        return {"ok": False, "error": f"Browser history read failed: {repr(e)}"}


def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()

