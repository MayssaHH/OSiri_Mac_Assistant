import os
import asyncio
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables if you have them in a .env file
load_dotenv()

# Configuration
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CHANNEL_NAME = "#trying-bot" 

async def test_slack_connection():
    if not SLACK_BOT_TOKEN:
        print("❌ Error: SLACK_BOT_TOKEN environment variable is not set.")
        return

    client = AsyncWebClient(token=SLACK_BOT_TOKEN)

    print(f"🔌 Connecting to Slack...")

    # 0. Resolve Channel Name to ID
    channel_id = None
    try:
        # List public channels to find the ID
        cursor = None
        while True:
            response = await client.conversations_list(cursor=cursor, types="public_channel,private_channel")
            for channel in response["channels"]:
                if channel["name"] == CHANNEL_NAME.lstrip("#"):
                    channel_id = channel["id"]
                    print(f"✅ Found Channel ID for {CHANNEL_NAME}: {channel_id}")
                    break
            if channel_id or not response.get("response_metadata", {}).get("next_cursor"):
                break
            cursor = response["response_metadata"]["next_cursor"]
    except SlackApiError as e:
        print(f"⚠️ Could not list channels: {e.response['error']}")

    # Fallback if lookup failed (e.g. no scopes to list channels)
    target = channel_id if channel_id else CHANNEL_NAME

    # 1. Send a Message
    print(f"\n📤 Sending test message to {target}...")
    try:
        response = await client.chat_postMessage(
            channel=target,
            text="Hello! This is a test message from the OSiri MAF Agent script."
        )
        print(f"✅ Message sent! Timestamp: {response['ts']}")
        # The response often contains the channel ID too
        if not channel_id:
            channel_id = response["channel"]
            print(f"ℹ️  Channel ID from response: {channel_id}")
            target = channel_id # Use this confirmed ID for reading
    except SlackApiError as e:
        print(f"❌ Failed to send message: {e.response['error']}")
        return

    # 2. Read Messages
    print(f"\n📥 Reading recent messages from {target}...")
    try:
        # conversations_history usually requires the ID, not the name
        response = await client.conversations_history(channel=target, limit=5)
        messages = response["messages"]
        print(f"✅ Retrieved {len(messages)} messages:")
        for msg in messages:
            user = msg.get("user", "Unknown")
            text = msg.get("text", "")
            ts = msg.get("ts", "")
            print(f"   - [{ts}] {user}: {text[:50]}...")
    except SlackApiError as e:
        print(f"❌ Failed to read messages: {e.response['error']}")
        if e.response['error'] == 'channel_not_found':
            print("   (Make sure the Bot is added to the channel and has 'channels:history' scope!)")
        elif e.response['error'] == 'missing_scope':
             print("   (Missing 'channels:history' or 'groups:history' scope)")

if __name__ == "__main__":
    asyncio.run(test_slack_connection())