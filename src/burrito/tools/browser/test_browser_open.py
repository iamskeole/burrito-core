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

url = "https://example.com"
url = "https://platform.openai.com/docs/api-reference/responses/input-items"
url = "https://www.antena3.ro/externe/parlamentul-european-a-suspendat-ratificarea-acordului-comercial-cu-sua-ca-raspuns-la-amenintarile-lui-trump-774198.html"

urls = [
    # "https://example.com",
    # "https://www.antena3.ro/externe/parlamentul-european-a-suspendat-ratificarea-acordului-comercial-cu-sua-ca-raspuns-la-amenintarile-lui-trump-774198.html",
    # "https://marcom.wwu.edu/how-create-anchor-jump-link#creatingananchor",
    # "https://www.w3schools.com/html/html_tables.asp",
    # "https://fapi.binance.com/fapi/v1/exchangeInfo",
    # "https://en.wikipedia.org/wiki/Artificial_intelligence",
    # "https://platform.openai.com/docs/api-reference/responses/input-items",
    # "https://platform.claude.com/docs/en/api/messages",
    # "https://platform.claude.com/docs/en/api/messages/create",
    # "https://google.com",
    # "https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information",
    # "https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/get-product-book",
    # "https://www.reuters.com/world/zelenskiy-says-territorial-issue-be-discussed-trilateral-talks-uae-2026-01-23/",
    # "https://www.washingtonpost.com/opinions/2026/01/23/greenland-trump-carney-davos/?itid=hp_opinions_p001_f017",
    'https://www.facebook.com/DianaSosoacaOficial/',
]

async def main():
    for url in urls:
        results = [] 

        async for msg in tool.open(
            id=url
        ):
            results.append(msg)

        last = results[0]
        txt = last.content[0].text
        print(txt)
        print(f"len after processing: {len(txt):,}")
        x = 1

if __name__ == "__main__":
    asyncio.run(main())