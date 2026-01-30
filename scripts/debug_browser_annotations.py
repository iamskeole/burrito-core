import asyncio
from burrito.tools.browser.tool import BurritoBrowser


url = "https://platform.openai.com/docs/api-reference/responses"

tool = BurritoBrowser()

text = "This is a placeholder to test annotations【0†L80-L90】. And a second one【0†L23-L44】"


async def main():
    hide_partial_citations = False
    current_citations = []
    current_citation_index = 0
    results = []
    async for msg in tool.open(id=url):
        results.append(msg)
    tool.open(id=url)

    normalized_text, _annotations, _has_partial_citations, current_citation_index = (
        tool.normalize_citations(
            text, hide_partial_citations, current_citations, current_citation_index
        )
    )
    print(f"browser.normalize_citations:\n # normalized_text: {normalized_text}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
