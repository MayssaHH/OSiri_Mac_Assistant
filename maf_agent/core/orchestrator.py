import json
from openai import OpenAI
from typing import List, Dict, Any

# Import our tools
from ..config import Config
from ..tools.slack_ops import SlackManager
from ..tools.email_ops import EmailManager

class Orchestrator:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.slack = SlackManager(token=Config.SLACK_BOT_TOKEN)
        self.email = EmailManager(
            email=Config.EMAIL_ACCOUNT,
            password=Config.EMAIL_PASSWORD,
            imap_server=Config.IMAP_SERVER,
            smtp_server=Config.SMTP_SERVER
        )
        
        # Define Tool Schema
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "read_slack",
                    "description": "Use this function to fetch recent messages from a specific Slack channel. Useful for summaries or checking status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_name": {"type": "string", "description": "The name of the channel, e.g. #general"},
                            "limit": {"type": "integer", "description": "Number of messages to fetch (default 10)"}
                        },
                        "required": ["channel_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_slack",
                    "description": "Use this function to post a message to a Slack channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_name": {"type": "string", "description": "The name of the channel, e.g. #random"},
                            "text": {"type": "string", "description": "The message content to post."}
                        },
                        "required": ["channel_name", "text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_email",
                    "description": "Fetch unread emails from the user's inbox. Returns a summary list of senders and subjects.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Max number of emails to fetch (default 5)"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send an email to a recipient.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to_email": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject line"},
                            "body": {"type": "string", "description": "Email body content"}
                        },
                        "required": ["to_email", "subject", "body"]
                    }
                }
            }
        ]

    def run_conversation(self, user_prompt: str):
        """Executes the agent loop: User -> LLM -> Tool -> LLM -> Response."""
        
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant capable of managing Slack and Email. "
                                          "When a tool returns raw data (like lists), summarize it nicely for the user."},
            {"role": "user", "content": user_prompt}
        ]

        # 1. First call to OpenAI
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=self.tools_schema,
                tool_choice="auto"
            )
        except Exception as e:
            return f"OpenAI API Error: {str(e)}"

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        # 2. Check if model wants to use tools
        if tool_calls:
            print(f" -> Model requested {len(tool_calls)} tool(s)...")
            messages.append(response_message)  # extend conversation with assistant's reply

            # 3. Execute tools
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    print(f"Error decoding arguments for {function_name}")
                    function_args = {}
                
                print(f" -> Executing {function_name} with {function_args}")
                
                tool_output = "Error: Tool not found"
                
                if function_name == "read_slack":
                    tool_output = self.slack.fetch_messages(**function_args)
                elif function_name == "send_slack":
                    tool_output = self.slack.post_message(**function_args)
                elif function_name == "read_email":
                    tool_output = self.email.fetch_unread(**function_args)
                elif function_name == "send_email":
                    tool_output = self.email.send_email(**function_args)

                # 4. Send tool output back to model
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": str(tool_output),
                })

            # 5. Second call to OpenAI to generate final response
            try:
                final_response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages
                )
                return final_response.choices[0].message.content
            except Exception as e:
                return f"OpenAI API Error during final response: {str(e)}"
        
        else:
            return response_message.content

