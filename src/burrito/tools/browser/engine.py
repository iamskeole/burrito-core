import textwrap
import asyncio
import logging
from typing import Optional
from datetime import datetime, date
import json
import aiohttp
from playwright.async_api import async_playwright, Browser, Route, Playwright

from lxml import html
import trafilatura

logger = logging.getLogger("browser_engine")


class BrowserEngine:
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _user_agent: str = ""  # getting from chromium inside playwright

    @classmethod
    async def start(cls):
        if cls._playwright is None:
            logger.info("Starting Playwright...")
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
            cls._user_agent = ua.replace("HeadlessChrome", "Chrome")

    @classmethod
    async def stop(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

    @classmethod
    async def fetch(
        cls, url: str, is_docs_website: bool, session: aiohttp.ClientSession
    ) -> str:
        # fast path (but disable for now, small overhead but ensure js always loads...)
        raw_html = None  # await cls._fetch_aiohttp(url, session)

        if raw_html:
            if cls._is_spa(raw_html):
                raw_html = None  # fallback to playwright

        # slow path (playwright) if needed
        if not raw_html:
            await cls.start()
            if not cls._browser:
                raise RuntimeError("Failed to start browser")

            context = await cls._browser.new_context(
                user_agent=cls._user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",  # Or match your server location
                has_touch=False,
                is_mobile=False,
                device_scale_factor=1,
                color_scheme="light",
            )

            # delete the `navigator.webdriver` property which is the #1 bot tell
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Overwrite the 'chrome' property so it looks consistent
                window.chrome = {
                    runtime: {}
                };
                
                // Pass the Permissions API test
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

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass

                title = await page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    logger.warning(f"Hit Cloudflare wall for {url}")
                    await asyncio.sleep(3)

                raw_html = await page.content()
            except Exception as e:
                await context.close()
            finally:
                await context.close()

        if raw_html is None:
            # empty html will suggest to the model there's probably a headless block
            raw_html = "<html></html>"
        return cls.preprocess_html(raw_html, is_docs_website, url)

    @classmethod
    async def _fetch_aiohttp(
        cls, url: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        try:
            async with session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": cls._user_agent,
                    "Accept-Language": "en-US,en;q=0.5",
                },
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(3),
            ) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type:
                        return await response.text()
        except Exception:
            pass
        return None

    @staticmethod
    def _is_spa(html: str) -> bool:
        if len(html) < 600:
            return True
        if '<div id="app"></div>' in html or '<div id="root"></div>' in html:
            return True
        return False

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
                fast=False,
                include_links=True,
                include_images=False,
                include_tables=True,
                include_comments=True,
                favor_precision=False,
                favor_recall=False,
                output_format="json",
                no_fallback=True,
                with_metadata=True,
                date_extraction_params=date_cfg,
            )
            loaded = json.loads(content) if content else None

            if loaded and len(loaded.get("text", "")) > 100:
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

    # TODO: cache, ie anthropic kills me on first processing
    @classmethod
    def preprocess_html(
        cls, html_content: str, is_docs_website: bool, base_url: str
    ) -> str:
        tree = None
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
            logger.warning(f"Error in preprocess_html: {str(e)}")
            pass

        if tree is not None and is_docs_website:
            preprocessed = cls._preprocess_docs_website(tree)
        else:
            preprocessed = cls._preprocess_standard_website(html_content, base_url)

        if preprocessed is None:
            return _empty
        return preprocessed
