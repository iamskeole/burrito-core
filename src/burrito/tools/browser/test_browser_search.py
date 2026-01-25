import asyncio

from gpt_oss.tools.simple_browser import SimpleBrowserTool

from burrito.tools.browser.backend import BurritoBackend

ENC_NAME = "o200k_base"

backend = BurritoBackend()

tool = SimpleBrowserTool(
    backend=backend,
    encoding_name=ENC_NAME,
    view_tokens=4096,
)

querries = [
    # "dentisti buni in brasov",
    "cine e presedintele frantei?",
    # "100 USD to EUR",
    # "Python (programming language)",
]

async def main():
    for q in querries:
        results = []

        async for msg in tool.search(
            query=q,
            top_n=10,
            source="web"
        ):
            results.append(msg)

        last = results[0]
        txt = last.content[0].text
        print(txt)
        print(f"len after processing: {len(txt):,}")
        x = 1


if __name__ == "__main__":
    asyncio.run(main())
