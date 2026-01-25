import asyncio
from gpt_oss.tools.simple_browser import SimpleBrowserTool

from burrito.tools.browser.backend import BurritoBackend

ENC_NAME = "o200k_base"

backend = BurritoBackend()

url = "https://www.bbc.com/news/articles/cm244zlnmkvo"

tool = SimpleBrowserTool(
    backend=backend,
    encoding_name=ENC_NAME,
    view_tokens=4096,
)

text = "This is a placeholder to test annotations【0†L80-L90】. And a second one【0†L23-L44】"

async def main():
    results = []
    async for msg in tool.open(
        id=url
    ):
        results.append(msg)
    tool.open(id=url)

    normalized_text, _annotations, _has_partial_citations = tool.normalize_citations(text, hide_partial_citations=True)
    x = 1

if __name__ == "__main__":
    asyncio.run(main())