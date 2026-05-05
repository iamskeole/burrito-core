import asyncio
import json
import random
import textwrap
from datetime import date
from functools import lru_cache
from typing import Optional

import httpx
import trafilatura
from gpt_oss.tools.simple_browser.backend import VIEW_SOURCE_PREFIX
from lxml import html
from playwright.async_api import (
    Browser,
    Playwright,
    Route,
    TimeoutError,
    async_playwright,
)

from burrito import __repo__, __version__
from burrito.common.config import settings
from burrito.common.logger import FastAPILogger


# app level singleton
class BurritoBrowserEngine:
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _logger = FastAPILogger.get_logger(__name__)
    _fetch_lock = asyncio.Lock()

    _user_agent_search: Optional[str] = f"burrito-browse/{__version__}; (+{__repo__})"
    _user_agent_browse: Optional[str] = f"burrito-search/{__version__}; (+{__repo__})"

    _width: int = random.randint(1600, 2000)
    _height: int = random.randint(600, 1200)

    _started = False

    @classmethod
    async def start(cls):
        if settings.BROWSER_BACKEND != "playwright":
            # httpx backend does not require Playwright initialization
            return
        if cls._playwright is not None:
            return

        cls._logger.info("Starting Playwright...")
        cls._playwright = await async_playwright().start()
        cls._browser = await cls._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--window-size=1920,1080",
                "--disable-http2",
                # "--disable-extensions",
                # "--mute-audio",
                # "--disable-images",
            ],
        )

        temp_page = await cls._browser.new_page()
        ua = await temp_page.evaluate("navigator.userAgent")
        ua = ua.replace("HeadlessChrome", "Chrome")

        ua_extra_browse = f"; compatible; burrito-browse/{__version__}; (+{__repo__})"
        ua_extra_search = f"; compatible; burrito-search/{__version__}; (+{__repo__})"

        cls._user_agent_browse = ua + ua_extra_browse
        cls._user_agent_search = ua + ua_extra_search

    @classmethod
    async def stop(cls):
        try:
            if cls._browser:
                await cls._browser.close()
        except Exception as e:
            if settings.DEBUG_BROWSER_ERRORS:
                cls._logger.warning(f"Browser closed forcefully during shutdown: {e}")
        finally:
            cls._browser = None

        try:
            if cls._playwright:
                await cls._playwright.stop()
        except Exception as e:
            if settings.DEBUG_BROWSER_ERRORS:
                cls._logger.warning(
                    f"Playwright stopped forcefully during shutdown: {e}"
                )
        finally:
            cls._playwright = None

    @classmethod
    async def fetch(cls, url: str, is_docs_website: bool, timeout: float) -> str:
        """Route fetch to the configured backend.

        When ``settings.BROWSER_BACKEND`` is ``"playwright"`` the original
        behaviour is preserved.  When it is ``"httpx"`` a lightweight
        implementation that performs a plain HTTP GET is used."""

        is_url = (
            url.startswith("http://")
            or url.startswith("https://")
            or url.startswith(VIEW_SOURCE_PREFIX)
        )
        if not is_url:
            raise ConnectionRefusedError(
                "The `browser.open` tool can only be used for opening **WEB** urls."
            )

        if settings.BROWSER_BACKEND == "httpx":
            return await cls.fetch_httpx(url, is_docs_website, timeout)

        async with cls._fetch_lock:
            if not cls._browser:
                await cls.start()
            if not cls._browser:
                raise RuntimeError("Failed to start browser")

            context = await cls._browser.new_context(
                user_agent=cls._user_agent_browse,
                viewport={"width": cls._width, "height": cls._height},
                locale=settings.BROWSER_LOCALE,
                timezone_id=settings.BROWSER_TIMEZONE,
                has_touch=False,
                is_mobile=False,
                device_scale_factor=1,
                color_scheme="light",
            )

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
            """)

            async def route_handler(route: Route):
                if route.request.resource_type in [
                    "image",
                    "media",
                    "font",
                    # "stylesheet", # some anti-bots check if stylesheets load, so we allow
                ]:
                    await route.abort()
                else:
                    await route.continue_()

            page = await context.new_page()
            await page.route("**/*", route_handler)

            raw_html = None
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                title = await page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    if settings.DEBUG_BROWSER_ERRORS:
                        cls._logger.warning(f"Hit Cloudflare wall for {url}")
                    await asyncio.sleep(3)
                raw_html = await page.content()
            except TimeoutError:
                raw_html = (
                    f"<html>Timeout error while loading {url}:\n"
                    f"wait_until='domcontentloaded' timed out after {timeout}ms.</html>"
                )
            finally:
                await context.close()
        return cls.preprocess_html(raw_html, is_docs_website, url)

    @classmethod
    async def fetch_httpx(cls, url: str, is_docs_website: bool, timeout: float) -> str:
        raw_html = None
        try:
            async with httpx.AsyncClient(timeout=timeout / 1000) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                raw_html = resp.text
        except httpx.HTTPError as exc:
            raw_html = f"<html>HTTP error while loading {url}: {exc}</html>"
        except Exception as exc:
            raw_html = f"<html>Unexpected error while loading {url}: {exc}</html>"
        return cls.preprocess_html(raw_html, is_docs_website, url)

    @staticmethod
    def _preprocess_docs_website(tree: html.HtmlElement) -> str:
        # prune line-number keywords or containing specific data-attributes.
        line_number_xpath = (
            "//*["
            "contains(@class, 'line-number') or "
            "contains(@class, 'lineno') or "
            "contains(@class, 'line-num') or "
            "contains(@class, 'syntax-ln') or "
            "contains(@class, 'gutter') or "
            "@data-line-number"
            "]"
        )

        for el in tree.xpath(line_number_xpath):
            el.drop_tree()

        # noise tag removal
        noise_tags = [
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "button",
            "input",
        ]
        for tag in noise_tags:
            for el in tree.iter(tag):
                el.drop_tree()

        clean = html.tostring(
            tree, encoding="unicode", pretty_print=True, method="html"
        )
        return str(clean)

    @classmethod
    def _preprocess_standard_website(cls, html_content: str, base_url: str) -> str:
        try:
            date_cfg = {
                "extensive_search": True,
                "original_date": True,
                "outputformat": "%Y-%m-%d",
                "min_date": "1984-10-09",
                "max_date": date.today().isoformat(),
            }
            content = trafilatura.extract(
                html_content,
                url=base_url,
                include_links=True,
                include_images=False,
                include_tables=True,
                include_comments=True,
                favor_precision=False,
                favor_recall=False,
                output_format="json",
                with_metadata=True,
                fast=False,
                date_extraction_params=date_cfg,
            )
            loaded = json.loads(content) if content else {}

            if not loaded or len(loaded.get("text", "")) < 100:
                return "<html></html>"

            title = loaded.get("title")
            source_name, host_name = (
                loaded.get("source-hostname"),
                loaded.get("hostname"),
            )
            source = (
                f"{source_name} ({host_name})"
                if source_name and host_name
                else base_url
            )
            body = textwrap.dedent(f"""
            # Excerpt: {loaded.get("excerpt")}
            # Date: {loaded.get("date") or loaded.get("filedate")}
            # Source: {source}
            # Author: {loaded.get("author") or None}
            # Tags: {loaded.get("tags") or None}

            # Article Content:
            {loaded.get("text")}

            ---

            # Comments:
            {loaded.get("comments") or None}
            """).strip()

            _html = f"<html><title>{title}</title><body>{body}</body></html>"
            return _html
        except Exception as e:
            return f"<html>{repr(e)}</html>"

    @classmethod
    # cache content processing, some kill cpu;
    # the open action itself is cached in browser tool that sticks by session
    @lru_cache(maxsize=2056)
    def preprocess_html(
        cls, html_content: Optional[str], is_docs_website: bool, base_url: str
    ) -> str:
        tree = None
        # empty html will suggest to the model there's probably a headless block
        _empty = "<html></html>"
        if not html_content:
            return _empty

        try:
            tree = html.fromstring(html_content)
            tree.make_links_absolute(base_url)
            html_updated = html.tostring(tree, encoding="unicode", method="html")
            if isinstance(html_updated, str):
                html_content = html_updated
        except Exception as e:
            if settings.DEBUG_BROWSER_ERRORS:
                cls._logger.warning(f"Error in preprocess_html: {str(e)}")
            pass

        if tree is not None and is_docs_website:
            preprocessed = cls._preprocess_docs_website(tree)
        else:
            preprocessed = cls._preprocess_standard_website(html_content, base_url)

        if preprocessed is None:
            return _empty
        return preprocessed
