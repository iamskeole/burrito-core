import asyncio
from gpt_oss.tools.python_docker.docker_tool import PythonTool
from openai_harmony import Message, Author, Role, TextContent

tool = PythonTool(
    execution_backend="dangerously_use_uv"
)

cmds = [
    'print("hello, world")',
    'print("hello, world)',
]

async def main():
    for cmd in cmds:
        print(f"Executing: {cmd}")
        msg = Message(
            author=Author(role=Role.ASSISTANT),
            content=[TextContent(text=cmd)],
            recipient="assistant"
        )

        try:
            async for out in tool.process(message=msg):
                print(f"Output: {out.content[0].text if out.content else 'No content'}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
