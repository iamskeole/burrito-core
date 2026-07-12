import asyncio

from burrito.tools.browser.tool import BurritoBrowser

tool = BurritoBrowser()
tool.view_tokens = 10241111
url = "https://openai.com/index/introducing-gpt-oss/"
is_docs_website = False
num_lines = -1


async def main():
    results = []
    async for msg in tool.open(
        id=url, is_docs_website=is_docs_website, num_lines=num_lines
    ):
        results.append(msg)
    print(f"browser.open ----------\n{results[0].content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
