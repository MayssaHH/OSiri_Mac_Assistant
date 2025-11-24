import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Setup logging to file
import logging
logging.basicConfig(
    filename='email_server.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Add root to path to import your existing tools
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from maf_agent.tools.email_ops import EmailManager

load_dotenv()

logging.info("Email MCP Server starting...")
logging.info(f"EMAIL_ACCOUNT: {os.getenv('EMAIL_ACCOUNT')}")
logging.info(f"IMAP_SERVER: {os.getenv('IMAP_SERVER')}")
logging.info(f"SMTP_SERVER: {os.getenv('SMTP_SERVER')}")

# Initialize Email Manager
email_manager = EmailManager(
    email=os.getenv("EMAIL_ACCOUNT"),
    password=os.getenv("EMAIL_PASSWORD"),
    imap_server=os.getenv("IMAP_SERVER"),
    smtp_server=os.getenv("SMTP_SERVER")
)

mcp = FastMCP(name="Email MCP Server")

@mcp.tool()
def read_email(limit: int = 5) -> str:
    """Fetch unread emails from the user's inbox."""
    logging.info(f"read_email called with limit={limit}")
    result = email_manager.fetch_unread(limit)
    logging.info(f"read_email result: {result[:100]}...")  # Log first 100 chars
    return result

@mcp.tool()
def send_email(to_email: str, subject: str, body: str) -> str:
    """Send an email to a recipient."""
    logging.info(f"send_email called to={to_email}, subject={subject}")
    result = email_manager.send_email(to_email, subject, body)
    logging.info(f"send_email result: {result}")
    return result

if __name__ == "__main__":
    mcp.run()

