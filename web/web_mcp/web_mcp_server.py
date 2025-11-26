"""
Web MCP Server
Exposes web-related tools via Model Context Protocol (MCP).
Tools: search_web, scrape_url, get_browser_history
"""
import os
import sqlite3
import shutil
import httpx
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient
import trafilatura
from trafilatura.settings import use_config
import json
from openai import OpenAI


mcp = FastMCP(name="Web MCP Server")

# Configure trafilatura with higher file size limit
trafilatura_config = use_config()
trafilatura_config.set("DEFAULT", "MAX_FILE_SIZE", "20000000")  # 20MB

# User-Agent for bypassing bot detection
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
FILTER_MODEL = "gpt-4o-mini"


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
# Tool 2: URL Scraping (Trafilatura + httpx for better headers)
# ============================================================================

def _fetch_with_headers(url: str, timeout: float = 30.0) -> str | None:
    """
    Fetch URL content with proper browser headers to bypass bot detection.
    Falls back to trafilatura if httpx fails.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except Exception as e:
        # Log and fall back to trafilatura
        print(f"httpx fetch failed: {e}, falling back to trafilatura")
        return trafilatura.fetch_url(url, config=trafilatura_config)


def _handle_arxiv_url(url: str) -> dict:
    """
    Special handling for arXiv URLs.
    Redirects PDF URLs to the abstract page which has readable HTML.
    """
    # Convert PDF URL to abstract URL
    # arxiv.org/pdf/2209.00796 -> arxiv.org/abs/2209.00796
    if "/pdf/" in url:
        abs_url = url.replace("/pdf/", "/abs/").rstrip(".pdf")
        return {"redirect": abs_url, "message": f"Redirecting arXiv PDF to abstract page: {abs_url}"}
    return None


@mcp.tool()
def scrape_url(url: str) -> dict:
    """
    Extracts clean text content from a specific URL.
    
    Handles special cases:
    - arXiv PDFs: Redirects to abstract page for readable content
    - Protected sites: Uses browser-like headers to bypass bot detection
    
    Args:
        url: The URL to scrape
        
    Returns:
        dict with 'ok', 'text', 'url', or 'error'
    """
    try:
        # Handle arXiv PDFs specially
        if "arxiv.org" in url:
            arxiv_result = _handle_arxiv_url(url)
            if arxiv_result and "redirect" in arxiv_result:
                url = arxiv_result["redirect"]
        
        # Check if it's a PDF URL (we can't extract text from PDFs with trafilatura)
        if url.lower().endswith(".pdf"):
            return {
                "ok": False, 
                "error": "PDF files cannot be scraped directly. Please provide the HTML page URL instead.",
                "suggestion": "For arXiv, use the abstract page (arxiv.org/abs/...) instead of the PDF."
            }
        
        # Fetch with proper headers
        downloaded = _fetch_with_headers(url)
        if not downloaded:
            return {"ok": False, "error": "Could not fetch URL (404, blocked, or invalid)"}
        
        # Extract text using trafilatura
        text = trafilatura.extract(downloaded, config=trafilatura_config)
        if not text:
            return {"ok": False, "error": "No text content found on page"}
        
        # Truncate very long content (keep first 10000 chars)
        if len(text) > 10000:
            text = text[:10000] + "\n\n[Content truncated...]"
        
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

@mcp.tool()
def filter_browser_history(history: list, intent: str, top_k: int = 1) -> dict:
    """
    Use an LLM to filter browser history based on user intent.
    Args:
        history: list of {timestamp,title,url} (most recent first)
        intent: e.g. "last article I read", "papers", "news", "blogs", etc.
        top_k: how many matching items to return
    Returns:
        {ok, selected, selected_indices, llm_notes}
    """
    if not history:
        return {"ok": True, "selected": [], "selected_indices": [], "llm_notes": "empty history"}

    # Shrink payload for the LLM
    items = [
        {"i": i, "title": (h.get("title") or ""), "url": (h.get("url") or "")}
        for i, h in enumerate(history)
    ]

    prompt = f"""
        You are selecting which browser history entries are actual readable and relevant content that matches the user's intent.

        User intent:
        {intent}

        History items (most recent first):
        {json.dumps(items, ensure_ascii=False)}

        Rules:
        - Prefer real articles/blogs/news/papers/tutorial pages.
        - Exclude chats (chatgpt, slack, discord), login pages

        Return STRICT JSON ONLY in the form:
        {{"selected_indices":[...], "notes":"short reason"}}

        Pick at most {top_k} indices.
        """.strip()

    try:
        resp = openai_client.chat.completions.create(
            model=FILTER_MODEL,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        data = json.loads(text)

        indices = data.get("selected_indices", [])
        selected = [history[i] for i in indices if isinstance(i, int) and 0 <= i < len(history)]

        return {
            "ok": True,
            "selected": selected,
            "selected_indices": indices,
            "llm_notes": data.get("notes", "")
        }

    except Exception as e:
        return {"ok": False, "error": f"LLM filter failed: {repr(e)}"}

def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()

