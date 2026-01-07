import logging
import os
import re
import base64
from typing import Dict, List, Tuple, Literal, Optional, Any
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from playwright.async_api import async_playwright, Browser, Route

logger = logging.getLogger("browser_engine")


class BrowserEngine:
    """
    Hybrid Engine: Uses aiohttp (Fast) for static sites and Playwright (Slow) for SPAs.
    Optimized for Speed: Linear O(N) DOM traversal with list buffering.
    """

    _playwright = None
    _browser: Optional[Browser] = None
    _session: Optional[aiohttp.ClientSession] = None

    # Configuration
    SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    @classmethod
    async def start(cls):
        """Call this on FastAPI startup."""
        if cls._session is None:
            # Persistent session for keep-alive connections
            timeout = aiohttp.ClientTimeout(total=5, connect=2)
            connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
            cls._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": cls.USER_AGENT},
            )

        if cls._playwright is None:
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--mute-audio",
                    "--disable-images",
                ],
            )

    @classmethod
    async def stop(cls):
        """Call this on FastAPI shutdown."""
        if cls._session:
            await cls._session.close()
            cls._session = None
        if cls._browser:
            await cls._browser.close()
        if cls._playwright:
            await cls._playwright.stop()

    # --- FAST MARKDOWN WALKER (O(N) Complexity) ---

    @staticmethod
    def _clean_and_convert_to_markdown(
        html_content: str, base_url: str
    ) -> Tuple[str, Dict[int, Dict[str, Any]]]:
        """
        Converts HTML to Markdown and extracts interactable elements in a single pass.
        """
        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception:
            soup = BeautifulSoup(html_content, "html.parser")

        # 1. Isolate Content (Avoid processing full DOM)
        content_node = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", id="bodyContent")
            or soup.find("div", class_="mw-parser-output")
            or soup.find("div", role="main")
            or soup.body
        )
        if not content_node:
            content_node = soup

        # 2. Initialize State
        buffer = []
        interactables_map = {}
        counter = [0]  # List hack for mutable closure

        # 3. Recursive Walk
        # We define this internally to close over 'buffer' and 'counter'
        # avoiding object overhead of a separate class
        def walk(node):
            if isinstance(node, NavigableString):
                if isinstance(node, Comment):
                    return
                text = str(node).replace("\n", " ")  # Flatten whitespace inside strings
                if not text.strip():
                    return
                buffer.append(text)
                return

            if node.name in [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                "form",
                "noscript",
                "iframe",
                "svg",
                "meta",
                "link",
            ]:
                return

            # Check noise classes (manual check is faster than soup.select inside recursion)
            if node.has_attr("class"):
                classes = node["class"]
                if any(
                    c in classes
                    for c in [
                        "sidebar",
                        "mw-editsection",
                        "noprint",
                        "ads",
                        "is-visually-hidden",
                        "sr-only",
                        "hidden",
                    ]
                ):
                    return
            if node.has_attr("id"):
                if node["id"] in ["toc", "mw-navigation"]:
                    return

            # Block Elements -> Add newlines
            is_block = node.name in [
                "p",
                "div",
                "h1",
                "h2",
                "h3",
                "h4",
                "li",
                "ul",
                "ol",
                "tr",
                "blockquote",
                "section",
                "article",
            ]

            # Pre-formatting
            prefix = ""
            if node.name in ["h1", "h2", "h3"]:
                prefix = "\n\n# "
            elif node.name == "li":
                prefix = "\n- "
            elif node.name in ["b", "strong"]:
                prefix = " **"
            elif node.name in ["i", "em"]:
                prefix = " *"
            elif node.name == "code":
                prefix = " `"
            elif node.name == "p":
                prefix = "\n\n"
            elif node.name == "br":
                prefix = "\n"

            if prefix:
                buffer.append(prefix)

            # Special Handling: Links
            if node.name == "a" and node.has_attr("href"):
                href = node["href"]
                full_url = urljoin(base_url, href)

                # We want to capture the inner text of the link
                # So we record the buffer length before recursing
                start_idx = len(buffer)

                for child in node.children:
                    walk(child)

                # Recover text added during recursion
                link_text = "".join(buffer[start_idx:]).strip()

                # Register if valid
                if not full_url.startswith(("javascript:", "mailto:", "#")) and (
                    len(link_text) > 0 or node.find("img")
                ):
                    counter[0] += 1
                    interactables_map[counter[0]] = {
                        "type": "LINK",
                        "url": full_url,
                        "original_text": link_text,
                    }
                    buffer.append(f" [{counter[0]}]")

                return  # Done with this node

            # Special Handling: Inputs
            if node.name == "input" and node.get("type") not in [
                "hidden",
                "submit",
                "image",
            ]:
                counter[0] += 1
                placeholder = (
                    node.get("placeholder", "") or node.get("name", "") or "Input"
                )
                buffer.append(f" [INPUT: {placeholder}] [{counter[0]}] ")

                selector = f"#{node['id']}" if node.has_attr("id") else node.name
                interactables_map[counter[0]] = {
                    "type": "INPUT",
                    "original_text": placeholder,
                    "selector": selector,
                }
                return

            # Special Handling: Buttons
            if node.name == "button":
                counter[0] += 1
                text = node.get_text(" ", strip=True)[:30]
                buffer.append(f" [BUTTON: {text}] [{counter[0]}] ")

                selector = f"#{node['id']}" if node.has_attr("id") else "button"
                interactables_map[counter[0]] = {
                    "type": "BUTTON",
                    "original_text": text,
                    "selector": selector,
                }
                return

            # Recurse for general elements
            for child in node.children:
                walk(child)

            # Post-formatting
            suffix = ""
            if node.name in ["b", "strong"]:
                suffix = "** "
            elif node.name in ["i", "em"]:
                suffix = "* "
            elif node.name == "code":
                suffix = "` "

            if suffix:
                buffer.append(suffix)

        # 4. Execute Walk
        walk(content_node)

        # 5. Join and Clean
        # Joining a list of strings is O(N)
        full_text = "".join(buffer)

        # Regex cleanup for excess whitespace
        full_text = re.sub(r"[ \t]+", " ", full_text)  # Collapse horizontal space
        full_text = re.sub(r"\n\s*\n", "\n\n", full_text)  # Normalize newlines

        return full_text.strip(), interactables_map

    async def _fetch_aiohttp(self, url: str) -> Optional[str]:
        try:
            if self._session is None:
                return None
            async with self._session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                },
                allow_redirects=True,
            ) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type:
                        return await response.text()
        except Exception:
            pass
        return None

    def _is_spa(self, html: str) -> bool:
        if len(html) < 600:
            return True
        if '<div id="app"></div>' in html or '<div id="root"></div>' in html:
            return True
        return False

    async def browse_url(self, url: str) -> Tuple[str, str, Dict[int, Dict], str]:
        # 1. Try Fast Path
        raw_html = await self._fetch_aiohttp(url)
        source = "FastPath"

        if raw_html:
            if self._is_spa(raw_html):
                raw_html = None

        # 2. Slow Path (Playwright)
        if not raw_html:
            source = "Playwright"
            if not self._browser:
                await self.start()
            context = await self._browser.new_context(user_agent=self.USER_AGENT)

            async def route_handler(route: Route):
                if route.request.resource_type in [
                    "image",
                    "media",
                    "font",
                    "stylesheet",
                ]:
                    await route.abort()
                else:
                    await route.continue_()

            page = await context.new_page()
            await page.route("**/*", route_handler)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=1000)
                except Exception:
                    pass

                raw_html = await page.content()
                await context.close()
            except Exception as e:
                await context.close()
                return f"Error loading page: {str(e)}", "Error", {}, ""

        # 3. Process
        try:
            title_match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE)
            title = title_match.group(1) if title_match else url

            markdown, interactables = self._clean_and_convert_to_markdown(raw_html, url)
            return markdown, title, interactables, raw_html
        except Exception as e:
            return f"Error processing content: {str(e)}", "Error", {}, ""

    async def perform_action(
        self, url: str, action_type: str, selector: str = None, value: str = None
    ) -> Tuple[str, str, Dict[int, Dict], str, str]:
        if not self._browser:
            await self.start()
        context = await self._browser.new_context(user_agent=self.USER_AGENT)
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            if action_type == "click_selector":
                await page.wait_for_selector(selector, state="visible", timeout=3000)
                await page.click(selector, timeout=5000)
            elif action_type == "type_selector":
                await page.wait_for_selector(selector, state="visible", timeout=3000)
                await page.fill(selector, value, timeout=5000)
                await page.keyboard.press("Enter")

            try:
                await page.wait_for_load_state("load", timeout=2000)
            except Exception:
                pass

            content = await page.content()
            title = await page.title()
            current_url = page.url

            markdown, interactables = self._clean_and_convert_to_markdown(
                content, current_url
            )
            return markdown, title, interactables, content, current_url
        except Exception as e:
            return f"Action Failed: {str(e)}", "Error", {}, "", url
        finally:
            await context.close()

    async def take_screenshot(self, url: str) -> str:
        if not self._browser:
            await self.start()
        context = await self._browser.new_context(user_agent=self.USER_AGENT)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            screenshot_bytes = await page.screenshot(type="jpeg", quality=70)
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception:
            return ""
        finally:
            await context.close()

    async def search(
        self, query: str, provider: Literal["searxng", "brave"] = "searxng"
    ) -> Tuple[str, Dict[int, Dict]]:
        if provider == "brave" and self.BRAVE_API_KEY:
            return await self._search_brave(query)
        return await self._search_searxng(query)

    async def _search_searxng(self, query: str) -> Tuple[str, Dict[int, Dict]]:
        params = {"q": query, "format": "json", "language": "en-US"}
        if self._session:
            try:
                async with self._session.get(
                    f"{self.SEARXNG_URL}/search", params=params, timeout=5
                ) as resp:
                    if resp.status != 200:
                        return f"Error: {resp.status}", {}
                    data = await resp.json()
            except Exception as e:
                return f"Search Connection Error: {e}", {}
        else:
            return "Error: Session not initialized", {}

        results = data.get("results", [])[:10]
        return self._format_search_results(results, "title", "url", "content")

    async def _search_brave(self, query: str) -> Tuple[str, Dict[int, Dict]]:
        headers = {"X-Subscription-Token": self.BRAVE_API_KEY}
        params = {"q": query, "count": 10}
        if self._session:
            async with self._session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=5,
            ) as resp:
                if resp.status != 200:
                    return f"Error: {resp.status}", {}
                data = await resp.json()
        else:
            return "Error: Session not initialized", {}
        results = data.get("web", {}).get("results", [])
        return self._format_search_results(results, "title", "url", "description")

    def _format_search_results(
        self, results: List[dict], title_key, url_key, snippet_key
    ) -> Tuple[str, Dict[int, Dict]]:
        lines = ["## Search Results"]
        interactables = {}
        for i, res in enumerate(results, 1):
            url = res.get(url_key)
            title = res.get(title_key, "No Title")
            snippet = res.get(snippet_key, "").replace("\n", " ")
            interactables[i] = {"type": "LINK", "url": url, "original_text": title}
            lines.append(f"{i}. **{title}**")
            lines.append(f"   {snippet}")
            lines.append(f"   Link ID: [{i}]")
            lines.append("")
        return "\n".join(lines), interactables

    @staticmethod
    def _extract_structure(soup: BeautifulSoup) -> str:
        headers = []
        for element in soup.find_all(["h1", "h2", "h3", "h4"]):
            level = int(element.name[1])
            indent = "  " * (level - 1)
            text = element.get_text(strip=True)
            if text:
                headers.append(f"{indent}- [{element.name.upper()}] {text}")
        return "\n".join(headers) if headers else "No headers found."

    @staticmethod
    def _extract_links_list(soup: BeautifulSoup, base_url: str) -> str:
        links_data = []
        counter = 0
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True) or "[Image/Icon]"
            counter += 1
            links_data.append(f"[{counter}] {text[:50]}... -> {a['href']}")
        return "\n".join(links_data)

    @staticmethod
    def _extract_main_content(soup: BeautifulSoup) -> str:
        # Re-use the optimized converter logic but simpler
        for tag in soup(
            [
                "nav",
                "footer",
                "header",
                "aside",
                "script",
                "style",
                "noscript",
                "iframe",
                "form",
            ]
        ):
            tag.decompose()
        main_tag = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", role="main")
            or soup.body
        )
        if not main_tag:
            return ""

        # Use simple get_text for speed
        text = main_tag.get_text(separator="\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text)

    async def run_javascript(self, url: str, script: str) -> str:
        if not self._browser:
            await self.start()
        context = await self._browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            result = await page.evaluate(script)
            return str(result)
        except Exception as e:
            return f"JS Error: {e}"
        finally:
            await context.close()
