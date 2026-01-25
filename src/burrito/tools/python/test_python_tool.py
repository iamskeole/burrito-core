import asyncio
import docker

from gpt_oss.tools.python_docker.docker_tool import PythonTool
from openai_harmony import Message, Author, Role, TextContent

def is_docker_available():
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


tool = PythonTool(
    execution_backend="docker"
)

cmds = [
    'print("hello, world")',
    'print("hello, world)',
]

async def main():
    if not is_docker_available():
        print("SKIPPING TEST: Docker is not running or not installed.")
        return
    for cmd in cmds:
        results = [] 

        msg = Message(
            author=Author(role=Role.ASSISTANT),
            content=[TextContent(text=cmd)],
            recipient="assistant"
        )

        async for out in tool.process(message=msg):
            results.append(out)

        last = results[0]
        txt = last.content[0].text
        print(txt)
        x = 1

if __name__ == "__main__":
    asyncio.run(main())