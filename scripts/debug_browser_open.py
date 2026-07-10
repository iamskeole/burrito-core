import asyncio

from burrito.tools.browser.tool import BurritoBrowser

tool = BurritoBrowser()
tool.view_tokens = 9999999
url = "https://developers.openai.com/api/docs/guides/migrate-to-responses"
is_docs_website = True
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
