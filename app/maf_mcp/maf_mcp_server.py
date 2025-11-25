import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Add the project root to sys.path so we can import maf_agent
# Assuming maf_mcp is at the root level alongside maf_agent
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from maf_agent.config import Config
from maf_agent.tools.slack_ops import SlackManager
from maf_agent.tools.email_ops import EmailManager

# Load environment variables
load_dotenv()

# Initialize Tools
# We'll initialize these lazily or globally. 
# Note: Ideally Config.validate() should be called, but we'll trust the env is set for now.

slack = SlackManager(token=Config.SLACK_BOT_TOKEN)
email = EmailManager(
    email=Config.EMAIL_ACCOUNT,
    password=Config.EMAIL_PASSWORD,
    imap_server=Config.IMAP_SERVER,
    smtp_server=Config.SMTP_SERVER
)

# Create MCP Server
mcp = FastMCP(name="MAF Agent MCP Server")

@mcp.tool()
def read_slack(channel_name: str, limit: int = 10) -> str:
    """Fetches recent messages from a Slack channel."""
    return slack.fetch_messages(channel_name, limit)

@mcp.tool()
def send_slack(channel_name: str, text: str) -> str:
    """Posts a message to a specific Slack channel."""
    return slack.post_message(channel_name, text)

@mcp.tool()
def read_email(limit: int = 5) -> str:
    """Fetch unread emails from the user's inbox."""
    return email.fetch_unread(limit)

@mcp.tool()
def send_email(to_email: str, subject: str, body: str) -> str:
    """Send an email to a recipient."""
    return email.send_email(to_email, subject, body)

def main():
    mcp.run()

if __name__ == "__main__":
    main()

