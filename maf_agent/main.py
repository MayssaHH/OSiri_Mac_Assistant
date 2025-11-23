import sys
import os

# Add the parent directory to sys.path so we can run from anywhere
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maf_agent.core.orchestrator import Orchestrator
from maf_agent.config import Config

def main():
    print("Initializing Multi-Agent Framework...")
    try:
        Config.validate()
        agent = Orchestrator()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Please check your .env file and ensure all required variables are set.")
        sys.exit(1)
    except Exception as e:
        print(f"Initialization Error: {e}")
        sys.exit(1)

    print("MAF Agent Online. Type 'exit' or 'quit' to stop.")
    print("-" * 50)

    while True:
        try:
            user_input = input("\n>> Enter command: ").strip()
            if user_input.lower() in ["exit", "quit"]:
                print("Shutting down.")
                break
            
            if not user_input:
                continue

            response = agent.run_conversation(user_input)
            print(f"\nAgent: {response}")

        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    main()

