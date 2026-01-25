import logging
import os
import re
from typing import Optional, List
import aiohttp
from aiohttp import ClientSession, ClientTimeout
import chz
from gpt_oss.tools.simple_browser.backend import Backend, BackendError
from gpt_oss.tools.simple_browser.page_contents import (
    PageContents,
    process_html,
    get_domain,
)

from .engine import BrowserEngine

from burrito.common.config import settings

logger = logging.getLogger("browser_backend")


@chz.chz(typecheck=True)
class BurritoBackend(Backend):
    source: str = chz.field(default="search engine or direct URL access")

    async def start(self):
        await BrowserEngine.start()

    async def stop(self):
        await BrowserEngine.stop()

    async def fetch(self, url: str, session: aiohttp.ClientSession) -> PageContents:
        try:
            text = await BrowserEngine.fetch(url, session)
            processed = process_html(html=text, url=url, title=None)

            if not processed.text:
                domain = get_domain(url).replace("www.", "")
                processed.text = f"No content available. {domain} is likely blocking headless access."
            return processed
        except Exception as e:
            raise BackendError(f"Error fetching or processing content: {str(e)}")

    async def _search_searxng(
        self, query: str, topn: int, session: ClientSession
    ) -> List[tuple]:
        payload = {
            "q": query,
            "safesearch": 0,
            "format": "json",
            "categories": "general,news,it,science,files,social media",
            "engines": "bing,brave,duckduckgo,google,yandex,baidu,startpage,yahoo,wikidata,wikipedia,wolframalpha",
        }
        headers = {
            "x-api-key": self._get_api_key(),
            "user-agent": settings.USER_AGENT_SEARCH,
        }

        async with session.post(
            f"{settings.SEARXNG_API_URL.replace('?format=json', '')}/search?format=json",
            data=payload,
            headers=headers,
        ) as resp:
            if resp.status != 200:
                logger.error(f"SearXNG error: {resp.status}")
                return []
            data = await resp.json()
            results = data.get("results", [])[:topn]
            return [
                (
                    res.get("title", "No Title"),
                    res.get("engine", "SearXNG"),
                    res.get("url"),
                    res.get("content", "").replace("\n", " "),
                )
                for res in results
            ]

    async def _search_brave(
        self, query: str, topn: int, session: ClientSession
    ) -> List[tuple]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.BRAVE_API_KEY,
            "User-Agent": settings.USER_AGENT_SEARCH,
        }
        params = {"q": query, "count": min(topn, 20)}

        async with session.get(
            settings.BRAVE_API_URL, headers=headers, params=params
        ) as resp:
            if resp.status != 200:
                logger.error(f"Brave API error {resp.status}: {await resp.text()}")
                return []

            data = await resp.json()
            results = data.get("web", {}).get("results", [])[:topn]
            return [
                (
                    res.get("title", "No Title"),
                    "Brave",
                    res.get("url"),
                    res.get("description", "").replace("\n", " "),
                )
                for res in results
            ]

    async def search(
        self, query: str, topn: int, session: aiohttp.ClientSession
    ) -> PageContents:
        titles_and_urls = []

        if settings.BRAVE_API_KEY:
            try:
                titles_and_urls = await self._search_brave(query, topn, session)
            except Exception as e:
                logger.error(f"Brave search failed, falling back: {e}")

        if not titles_and_urls:
            titles_and_urls = await self._search_searxng(query, topn, session)

        if not titles_and_urls:
            html_page = "<html><body><h1>No results found.</h1></body></html>"
        else:
            list_items = "".join(
                [
                    f"<li><a href='{url}'>{title}</a> {summary} [Source: {engine} (search engine)]</li>"
                    for title, engine, url, summary in titles_and_urls
                ]
            )
            html_page = f"""
<html><body>
<h1>Search Results</h1>
<ul>
{list_items}
</ul>
</body></html>
"""
        return process_html(
            html=html_page,
            url="",
            title=query,
            display_urls=True,
        )

    def _get_api_key(self) -> str:
        return settings.BRAVE_API_KEY or ""
