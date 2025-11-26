"""
MAF MCP Server
Exposes Slack and Gmail tools via Model Context Protocol (MCP).
Tools: send_slack_message, read_slack_messages, send_outlook_email, read_outlook_emails
"""
import os
import json
import time
import base64
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Slack SDK
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Gmail API
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

mcp = FastMCP(name="MAF MCP Server")

# ============================================================================
# Initialization / Helpers
# ============================================================================

def get_slack_client():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        return None
    return WebClient(token=token)

def get_gmail_service():
    """Authenticate and return Gmail service using local token.json"""
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send"
    ]
    creds = None
    
    # Look for token.json in typical locations
    token_locations = ["maf_agent/token.json", "token.json"]
    token_path = None
    
    for path in token_locations:
        if os.path.exists(path):
            token_path = path
            break
            
    if token_path:
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                return None
        else:
            # We cannot run interactive auth inside the MCP server easily.
            # User must run test_gmail.py first to generate token.json
            return None

    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except HttpError:
        return None

# ============================================================================
# Tool 1: Slack Integration (Real)
# ============================================================================

@mcp.tool()
def send_slack_message(channel: str, text: str) -> dict:
    """
    Sends a message to a Slack channel.
    """
    client = get_slack_client()
    if not client:
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}

    try:
        # Try sending directly first (assuming channel is ID or name)
        response = client.chat_postMessage(channel=channel, text=text)
        return {
            "ok": True,
            "ts": response["ts"],
            "channel": response["channel"],
            "message": "Message sent successfully"
        }
    except SlackApiError as e:
        return {"ok": False, "error": f"Slack API Error: {e.response['error']}"}

@mcp.tool()
def read_slack_messages(channel: str, limit: int = 10) -> dict:
    """
    Reads recent messages from a Slack channel.
    Note: If 'channel' is a name (e.g. #general), we attempt to resolve it to an ID.
    """
    client = get_slack_client()
    if not client:
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}

    channel_id = channel
    
    # If channel starts with #, try to resolve ID
    if channel.startswith("#"):
        target_name = channel.lstrip("#")
        try:
            cursor = None
            found = False
            while not found:
                # Searching public and private channels
                response = client.conversations_list(
                    cursor=cursor, 
                    types="public_channel,private_channel",
                    limit=1000
                )
                for ch in response["channels"]:
                    if ch["name"] == target_name:
                        channel_id = ch["id"]
                        found = True
                        break
                if found or not response.get("response_metadata", {}).get("next_cursor"):
                    break
                cursor = response["response_metadata"]["next_cursor"]
        except SlackApiError:
            # If list fails (e.g. missing scope), fall back to trying raw channel name
            pass

    try:
        response = client.conversations_history(channel=channel_id, limit=limit)
        messages = response["messages"]
        
        formatted = []
        for msg in messages:
            # Filter out subtype messages if needed, but keeping basic info
            formatted.append({
                "user": msg.get("user", "bot/unknown"),
                "text": msg.get("text", ""),
                "ts": msg.get("ts", "")
            })
            
        return {
            "ok": True,
            "messages": formatted,
            "channel": channel_id
        }
    except SlackApiError as e:
         return {"ok": False, "error": f"Slack API Error: {e.response['error']}"}


# ============================================================================
# Tool 2: Outlook (Gmail) Integration (Real)
# ============================================================================

@mcp.tool()
def send_outlook_email(to_email: str, subject: str, body: str) -> dict:
    """
    Sends an email via Gmail (keeping function name 'outlook' for compat).
    """
    service = get_gmail_service()
    if not service:
        return {"ok": False, "error": "Gmail service not available. Run test_gmail.py to auth."}

    try:
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to_email
        message["From"] = "me"
        message["Subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}
        
        sent_message = (
            service.users()
            .messages()
            .send(userId="me", body=create_message)
            .execute()
        )
        return {
            "ok": True,
            "id": sent_message["id"],
            "recipient": to_email,
            "status": "Sent"
        }
    except HttpError as error:
        return {"ok": False, "error": f"Gmail API Error: {error}"}


@mcp.tool()
def read_outlook_emails(limit: int = 5) -> dict:
    """
    Reads recent emails from Gmail (keeping function name 'outlook' for compat).
    """
    service = get_gmail_service()
    if not service:
         return {"ok": False, "error": "Gmail service not available. Run test_gmail.py to auth."}

    try:
        results = service.users().messages().list(userId="me", maxResults=limit).execute()
        messages = results.get("messages", [])

        formatted = []
        if not messages:
            return {"ok": True, "emails": []}

        for msg in messages:
            txt = service.users().messages().get(userId="me", id=msg["id"]).execute()
            payload = txt.get("payload", {})
            headers = payload.get("headers", [])
            
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "(Unknown)")
            snippet = txt.get("snippet", "")
            
            formatted.append({
                "subject": subject,
                "from": sender,
                "snippet": snippet,
                "id": msg["id"]
            })
            
        return {
            "ok": True,
            "emails": formatted
        }

    except HttpError as error:
        return {"ok": False, "error": f"Gmail API Error: {error}"}


def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()
