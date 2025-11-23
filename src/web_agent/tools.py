import os
import sqlite3
import shutil
from datetime import datetime, timedelta
from tavily import TavilyClient, MissingAPIKeyError
import trafilatura

def search_web(query: str) -> str:
    """
    Searches the web for information using Tavily.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY is missing in .env file."

    try:
        tavily = TavilyClient(api_key)
        # search_depth="advanced" is key for agents
        response = tavily.search(query=query)
        
        results = response.get('results', [])
        if not results:
            return "Search returned no results."

        # Extract context
        context = []
        for result in results:
            title = result.get('title', 'No Title')
            url = result.get('url', 'No URL')
            content = result.get('content', '')
            context.append(f"Title: {title}\nURL: {url}\nContent: {content}\n")
            
        return "\n---\n".join(context)

    except MissingAPIKeyError:
        return "Error: Invalid or Missing Tavily API Key."
    except Exception as e:
        # Convert exception to string to let the agent know what happened
        return f"Search Tool Failed: {repr(e)}"

def scrape_url(url: str) -> str:
    """
    Extracts text content from a specific URL.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded: 
            return "Error: Could not fetch URL (404, blocked, or invalid URL)."
        text = trafilatura.extract(downloaded)
        return text if text else "Error: No text found on page."
    except Exception as e:
        return f"Scrape Tool Failed: {repr(e)}"

def get_browser_history(hours: int = 24, count: int = 10, domain: str = None) -> str:
    """
    Retrieves recent browser history from Safari or Chrome.
    
    Args:
        hours: Look back this many hours (default: 24 for today)
        count: Maximum number of results to return (default: 10)
        domain: Optional domain filter (e.g., "github.com", "youtube.com")
    
    Returns:
        Formatted list of URLs with titles and timestamps, or error message.
    
    Examples:
        - get_browser_history(hours=24, count=5) -> Last 5 URLs from today
        - get_browser_history(hours=1, count=10, domain="github.com") -> GitHub visits in last hour
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
            return f"Error: Could not access Chrome history: {e}"
    elif os.path.exists(safari_db):
        db_path = safari_db
        browser = "safari"
    else:
        return "Error: No supported browser history found (Safari or Chrome)."
    
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
            # Chrome uses microseconds since 1601-01-01 (Windows epoch)
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
            return f"No browser history found in the last {hours} hours{filter_msg}."
        
        # Format output
        output = []
        for url, title, timestamp in results:
            title = title or "No Title"
            # Convert timestamp to human-readable format
            if browser == "safari":
                visit_time = datetime(2001, 1, 1) + timedelta(seconds=timestamp)
            else:  # chrome
                visit_time = datetime(1601, 1, 1) + timedelta(microseconds=timestamp)
            
            time_str = visit_time.strftime("%Y-%m-%d %H:%M:%S")
            output.append(f"[{time_str}] {title}\nURL: {url}\n")
        
        return "\n---\n".join(output)
    
    except Exception as e:
        return f"Error reading browser history: {repr(e)}"
