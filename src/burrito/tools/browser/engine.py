import asyncio
import logging
from typing import Optional

import aiohttp
from playwright.async_api import async_playwright, Browser, Route, Playwright

from lxml import html
logger = logging.getLogger("browser_engine")

HARD_TARGETS = [
    "reuters.com", "bloomberg.com", "wsj.com", 
    "nytimes.com", "ft.com", "discord.com", "twitter.com",
    "washingtonpost.com",
]


class BrowserEngine:
    """
    Engine for rendering HTML content to Markdown and managing the Playwright lifecycle.
    Focuses on clean extraction, post-processing, and fetching.
    """

    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _user_agent: str = "" # getting from chromium inside playwright

    @classmethod
    async def start(cls):
        """Initializes Playwright and launches the browser if not already started."""
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

            # 2. Ask the browser for its own User Agent string
            ua = await temp_page.evaluate("navigator.userAgent")
            
            # 3. Clean it (Just in case "Headless" sneaked in, though unlikely with headless=False)
            cls._user_agent = ua.replace("HeadlessChrome", "Chrome")
            
            logger.info(f"Native User-Agent detected: {cls._user_agent}")
            x = 1

    @classmethod
    async def stop(cls):
        """Closes the browser and stops Playwright."""
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

    @classmethod
    async def fetch(cls, url: str, session: aiohttp.ClientSession) -> str:
        """
        Fetches the content of a URL using aiohttp or Playwright.
        Returns a tuple of (raw_html, markdown, urls_map).
        """

        is_hard_target = True #any(target in url for target in HARD_TARGETS)
        raw_html = None

        if not is_hard_target:
            raw_html = await cls._fetch_aiohttp(url, session)

        if raw_html:
            if cls._is_spa(raw_html):
                raw_html = None  # Fallback to Playwright

        # 2. Slow Path (Playwright) if needed
        if not raw_html:
            await cls.start()
            if not cls._browser:
                raise RuntimeError("Failed to start browser")

            context = await cls._browser.new_context(
                    user_agent=cls._user_agent,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/New_York", # Or match your server location
                    has_touch=False,
                    is_mobile=False,
                    device_scale_factor=1,
                    color_scheme="light"
                )
            
            # STEALTH UPGRADE 3: Script Injection
            # This deletes the `navigator.webdriver` property which is the #1 bot tell.
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
                await page.goto(url, wait_until="domcontentloaded", timeout=3000)
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
                # raise Exception(f"Error loading page: {str(e)}")
                raw_html = "<html></html>" # blank html will tell the agent to avoid restricted headless browsing
            finally:
                await context.close()

        return cls.preprocess_html(raw_html, url)

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

    # TODO: cache, ie anthropic kills me on first processing
    @staticmethod
    def preprocess_html(html_content: str, base_url: str) -> str:
        tree = html.fromstring(html_content)

        # 1. Generic XPath to catch any element with a class containing line-number keywords
        # or containing specific data-attributes.
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

        # 2. Your standard noise tag removal
        noise_tags = ["script", "style", "nav", "footer", "header", "aside", "button", "input"]
        for tag in noise_tags:
            for el in tree.iter(tag):
                el.drop_tree()

        # 3. Output cleaned HTML
        clean = html.tostring(tree, encoding='unicode', pretty_print=True, method='html')
        return clean
