import time
import asyncio
from pathlib import Path

from terminal_agent import build_agent
from terminal_client import terminal_mcp


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


async def run_task(agent, task: str):
    print("\n==============================")
    print("TASK:", task)
    print("==============================")
    result = await agent.run(task)
    print("\n--- Agent reply ---")
    print(result.text)
    return result.text


async def main():
    agent = build_agent()

    # Create a unique sandbox on Desktop for tests
    desktop = Path.home() / "Desktop"
    sandbox = desktop / f"terminal_agent_test_{int(time.time())}"
    sandbox.mkdir(parents=True, exist_ok=True)

    print(f"\nSandbox: {sandbox}")

    # Test 1: create folder + file
    folder1 = sandbox / "task1_folder"
    file1 = folder1 / "hello.py"

    task1 = (
        f"Create a folder at {folder1} and inside it create a python file hello.py "
        f"that prints 'hello world'."
    )
    await run_task(agent, task1)

    # Verify Test 1
    assert folder1.exists() and folder1.is_dir(), "Test1 failed: folder not created"
    assert file1.exists(), "Test1 failed: hello.py not created"
    content1 = read_text(file1)
    assert "print" in content1.lower(), "Test1 failed: hello.py doesn't contain print"
    print("Test1 passed")

    # Test 2: make a folder, create a text file and write My name is Mayssa in it
    folder2 = sandbox / "task2_folder"
    file2 = folder2 / "name.txt"

    task2 = (
        f"Make a folder {folder2}. Then go inside it and create a file called name.txt and write inside the text file My name is Mayssa."
    )
    await run_task(agent, task2)

    # Verify Test 2
    assert folder2.exists() and folder2.is_dir(), "Test2 failed: folder not created"
    assert file2.exists(), "Test2 failed: name.txt not created"
    content2 = read_text(file2)
    assert "my name is mayssa" in content2.lower(), f"Test2 failed: name.txt content incorrect. Got: {content2}"
    print("Test2 passed")

    # Test 3: make a folder, create a python code that prints My name is Mayssa
    folder3 = sandbox / "task3_folder"
    file3 = folder3 / "code.py"

    task3 = (
        f"Make a folder {folder3}. Then go inside it and create a file called code.py and write inside the file the following code: print('My name is Mayssa'). Then run the file with python and tell me the output."
    )
    reply3 = await run_task(agent, task3)

    # Verify Test 3
    assert folder3.exists() and folder3.is_dir(), "Test3 failed: folder not created"
    assert file3.exists(), "Test3 failed: code.py not created"
    content3 = read_text(file3)
    assert "My name is Mayssa" in content3, "Test3 failed: code.py doesn't print My name is Mayssa"

    # Verify Test 3 agent reported output
    assert "My name is Mayssa" in reply3, "Test3 failed: agent didn't report running output"
    print("Test3 passed")

    print("\nAll TerminalAssistant tests passed.")
    print(f"Artifacts left in: {sandbox}")
    
    # Clean up MCP client connection
    await terminal_mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
