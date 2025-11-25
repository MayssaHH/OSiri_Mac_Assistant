import json
from typing import List, Any, Dict
from openai import OpenAI, AsyncOpenAI

class AgentResult:
    def __init__(self, text: str):
        self.text = text

class Agent:
    def __init__(self, client: AsyncOpenAI, name: str, instructions: str, tools: List[Any]):
        self.client = client
        self.name = name
        self.instructions = instructions
        self.tools = tools
        self.tool_map = {t._ai_metadata["name"]: t for t in tools}
        
    async def run(self, user_input: str) -> Any:
        messages = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": user_input}
        ]
        
        # Convert tools to OpenAI format
        openai_tools = []
        for t in self.tools:
            meta = t._ai_metadata
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": meta["name"],
                    "description": meta["description"],
                    "parameters": meta["parameters"]
                }
            })
            
        # Call OpenAI
        # Use a loop to handle multiple turns of tool calls
        while True:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None
            )
            
            msg = response.choices[0].message
            
            # If no tools called, we are done
            if not msg.tool_calls:
                return AgentResult(msg.content or "")
            
            # If tools called, execute them and loop again
            messages.append(msg) # Add assistant's tool request to history
            
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                # Execute python function
                if fn_name in self.tool_map:
                    try:
                        result = await self.tool_map[fn_name](**args)
                    except Exception as e:
                        result = f"Error: {str(e)}"
                else:
                    result = "Error: Tool not found"
                    
                # Add result to history
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": fn_name,
                    "content": str(result)
                })

class OpenAIChatClient:
    def __init__(self, api_key: str, model_id: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_id = model_id
        
    def create_agent(self, name: str, instructions: str, tools: List[Any] = [], middleware: List[Any] = None):
        return Agent(self.client, name, instructions, tools)
