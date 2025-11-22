import asyncio
from terminal_agent import run_task_with_plan

async def main():
    task = input("\nTask for TerminalAssistant: ").strip()
    await run_task_with_plan(task, auto_approve=False)

if __name__ == "__main__":
    asyncio.run(main())
