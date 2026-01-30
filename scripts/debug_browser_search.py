import asyncio

from burrito.tools.browser.tool import BurritoBrowser

tool = BurritoBrowser()
query = "Python (programming language)"


async def main():
    results = []
    async for msg in tool.search(query=query, top_n=10, source="web"):
        results.append(msg)
    print(f"browser.search:\n{results[0].content[0].text}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
