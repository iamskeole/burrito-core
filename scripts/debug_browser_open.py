import asyncio

from burrito.tools.browser.tool import BurritoBrowser

tool = BurritoBrowser()
url = "https://platform.openai.com/docs/api-reference/responses"


async def main():
    results = []
    async for msg in tool.open(id=url):
        results.append(msg)

    print(f"browser.open result:\n{results[0].content[0].text}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
