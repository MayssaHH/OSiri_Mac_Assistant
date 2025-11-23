import os
import sys
import asyncio
from dotenv import load_dotenv
from .agent import create_web_agent

# Load environment variables from .env file
load_dotenv()

async def main():
    # Check if a query is provided via command line
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        mode = "cli"
    else:
        query = None
        mode = "interactive"

    if mode == "interactive":
        print(">>> OSiri Web Agent Initialized (MAF Powered)")
        print(">>> Type 'exit' to quit.\n")
    
    # Create the agent
    try:
        web_agent = create_web_agent()
    except Exception as e:
        print(f"Error initializing agent: {e}")
        print("Check your API keys in .env file.")
        return
    
    if mode == "cli":
        # Run single query and exit
        try:
            print(f"User: {query}")
            print("... OSiri Thinking ...")
            response = await web_agent.run(query)
            # Extract message content safely
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                 # response.message.content might be a list of content blocks
                 content_blocks = response.message.content
                 text = ""
                 if isinstance(content_blocks, list):
                     for block in content_blocks:
                         if hasattr(block, 'text'):
                             text += block.text
                         else:
                             text += str(block)
                 else:
                     text = str(content_blocks)
                 print(f"\nOSiri: {text}\n")
            else:
                 print(f"\nOSiri: {response}\n")
        except Exception as e:
            print(f"Error during execution: {e}")
        return

    # Main Loop (Interactive)
    while True:
        try:
            user_input = input("User: ")
        except EOFError:
            break

        if user_input.lower() in ["exit", "quit"]:
            print("OSiri: Goodbye!")
            break
            
        if not user_input.strip():
            continue

        print("... OSiri Thinking ...")
        
        try:
            response = await web_agent.run(user_input)
            # Extract message content safely (same logic as above)
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                 content_blocks = response.message.content
                 text = ""
                 if isinstance(content_blocks, list):
                     for block in content_blocks:
                         if hasattr(block, 'text'):
                             text += block.text
                         else:
                             text += str(block)
                 else:
                     text = str(content_blocks)
                 print(f"\nOSiri: {text}\n")
            else:
                 print(f"\nOSiri: {response}\n")
            
        except Exception as e:
            print(f"Error during execution: {e}")

if __name__ == "__main__":
    asyncio.run(main())
