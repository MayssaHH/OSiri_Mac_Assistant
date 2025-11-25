import time
from typing import List, Dict, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class SlackManager:
    def __init__(self, token: str):
        self.client = WebClient(token=token)
        self._channel_cache: Dict[str, str] = {}

    def _get_channel_id(self, channel_name: str) -> Optional[str]:
        """Resolves a channel name (e.g., '#general') to a Channel ID."""
        # Strip '#' if present
        clean_name = channel_name.lstrip('#')
        
        # Check cache first
        if clean_name in self._channel_cache:
            return self._channel_cache[clean_name]

        try:
            # Slack API pagination might be needed for large workspaces
            # For simplicity, we fetch the first 1000 public channels
            response = self.client.conversations_list(limit=1000, types="public_channel,private_channel")
            if response.get("channels"):
                for channel in response["channels"]:
                    if channel["name"] == clean_name:
                        self._channel_cache[clean_name] = channel["id"]
                        return channel["id"]
        except SlackApiError as e:
            print(f"Error resolving channel name: {e}")
        
        return None

    def fetch_messages(self, channel_name: str, limit: int = 10) -> str:
        """Fetches recent messages from a Slack channel."""
        channel_id = self._get_channel_id(channel_name)
        if not channel_id:
            return f"Error: Could not find channel named '{channel_name}'."

        try:
            result = self.client.conversations_history(channel=channel_id, limit=limit)
            messages = result.get("messages", [])
            
            formatted_output = []
            for msg in messages:
                user = msg.get("user", "Unknown")
                text = msg.get("text", "")
                ts = msg.get("ts", "")
                formatted_output.append(f"[{ts}] User {user}: {text}")
            
            return "\n".join(formatted_output) if formatted_output else "No messages found."

        except SlackApiError as e:
            if e.response['error'] == 'not_in_channel':
                 return f"Error: The bot is not in the channel #{channel_name}. Please add it."
            return f"Slack API Error: {e.response['error']}"

    def post_message(self, channel_name: str, text: str) -> str:
        """Posts a message to a specific Slack channel."""
        channel_id = self._get_channel_id(channel_name)
        if not channel_id:
            return f"Error: Could not find channel named '{channel_name}'."

        try:
            self.client.chat_postMessage(channel=channel_id, text=text)
            return f"Successfully posted to #{channel_name}."
        except SlackApiError as e:
            return f"Slack API Error: {e.response['error']}"

