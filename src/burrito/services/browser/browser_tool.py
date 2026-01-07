import asyncio
import inspect
from typing import Dict, Optional, Any, Union, List, Callable
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from .browser_engine import BrowserEngine
from .query_processor import QueryProcessor


class BrowserState(BaseModel):
    current_url: Optional[str] = None
    current_markdown: str = ""
    current_interactables: Dict[int, Dict[str, Any]] = Field(default_factory=dict)
    current_html: str = ""
    scroll_position: int = 0
    history: List[str] = Field(default_factory=list)
    history_index: int = -1


class BrowserTool:
    """
    Stateful Interface for the Agent.
    Supports atomic "One-Shot" actions by accepting optional URLs in inspection methods.
    """

    def __init__(self):
        self.engine = BrowserEngine()
        self.state = BrowserState()
        self.max_view_lines = 80

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatcher: Maps string actions to methods and handles argument unpacking.
        Returns standardized API response format.
        """
        # Note: We now pass p.get("url") to inspection tools to allow auto-visiting.
        actions: Dict[str, Callable] = {
            "visit": lambda p: self.navigate(p["url"]),
            "search": lambda p: self.search(p["query"]),
            "interact": lambda p: self.interact(
                p.get("action", "click"), int(p["id"]), p.get("value")
            ),
            # Updated to accept optional URL for one-shot execution
            "scan": lambda p: self.scan_page(p["query"], p.get("url")),
            "structure": lambda p: self.get_document_structure(p.get("url")),
            "links": lambda p: self.get_links_only(p.get("url")),
            "main_content": lambda p: self.get_main_content(p.get("url")),
            "screenshot": lambda p: self.screenshot(p.get("url")),
            "javascript": lambda p: self.evaluate_javascript(p["script"], p.get("url")),
            "scroll": lambda p: self.scroll(p.get("direction", "down")),
            "back": lambda p: self.go_back(),
            "forward": lambda p: self.go_forward(),
        }

        handler = actions.get(action)
        if not handler:
            raise ValueError(f"Unknown browser action: '{action}'")

        try:
            result_proxy = handler(params)

            # Handle Async vs Sync (inspection tools are now async due to potential visit)
            if inspect.iscoroutine(result_proxy):
                result = await result_proxy
            else:
                result = result_proxy

            if isinstance(result, dict) and "type" in result:
                return result

            # from burrito.common.utils import simple_markdown_renderer
            # print(simple_markdown_renderer(result))

            return {"type": "text", "content": result}

        except KeyError as e:
            return {"type": "error", "content": f"Missing parameter: {str(e)}"}
        except Exception as e:
            return {"type": "error", "content": f"Execution error: {str(e)}"}

    # --- Core Navigation ---

    async def search(self, query: str) -> str:
        """Search the web."""
        markdown, interactables = await self.engine.search(query)
        self._set_page_content(f"search://{query}", markdown, interactables, "")
        self._record_visit(f"search://{query}")
        return self._get_view_window()

    async def navigate(self, url: str) -> str:
        """Directly visit a URL."""
        markdown, title, interactables, raw_html = await self.engine.browse_url(url)
        self._set_page_content(
            url, f"# {title}\nURL: {url}\n\n{markdown}", interactables, raw_html
        )
        self._record_visit(url)
        return self._get_view_window()

    async def interact(self, action: str, id: int, value: Optional[str] = None) -> str:
        if err := self._validate_page_state(require_html=False):
            return err

        if id not in self.state.current_interactables:
            return f"Error: ID [{id}] not found in current view."

        target = self.state.current_interactables[id]
        target_type = target.get("type")

        # 1. Handle Link Navigation
        if target_type == "LINK":
            url = target.get("url")
            # Reuse navigate logic
            return await self.navigate(url)

        # 2. Handle Button/Input
        current_url = self.state.current_url
        if not current_url or current_url.startswith("search://"):
            return "Error: Cannot interact with page elements on a search result. Click a link first."

        action_type = "click_selector"
        selector = target.get("selector")

        if target_type == "INPUT":
            if action != "type":
                return "Error: You must use action='type' for Inputs."
            if not value:
                return "Error: Value required for type action."
            action_type = "type_selector"

        (
            markdown,
            title,
            interactables,
            raw_html,
            new_url,
        ) = await self.engine.perform_action(
            url=current_url, action_type=action_type, selector=selector, value=value
        )

        self._set_page_content(
            new_url, f"# {title}\nURL: {new_url}\n\n{markdown}", interactables, raw_html
        )

        if new_url != current_url:
            self._record_visit(new_url)

        return self._get_view_window()

    # --- Inspection Tools (Now Async & Auto-Visiting) ---

    async def scan_page(
        self, query: Union[str, Dict[str, Any]], url: Optional[str] = None
    ) -> str:
        if err := await self._ensure_url_visited(url, require_html=False):
            return err
        return QueryProcessor.filter_markdown(self.state.current_markdown, query)

    async def get_document_structure(self, url: Optional[str] = None) -> str:
        if err := await self._ensure_url_visited(url, require_html=True):
            return err
        soup = BeautifulSoup(self.state.current_html, "html.parser")
        return self.engine._extract_structure(soup)

    async def get_links_only(self, url: Optional[str] = None) -> str:
        if err := await self._ensure_url_visited(url, require_html=True):
            return err
        soup = BeautifulSoup(self.state.current_html, "html.parser")
        return self.engine._extract_links_list(soup, self.state.current_url or "")

    async def get_main_content(self, url: Optional[str] = None) -> str:
        if err := await self._ensure_url_visited(url, require_html=True):
            return err
        soup = BeautifulSoup(self.state.current_html, "html.parser")
        return self.engine._extract_main_content(soup)

    async def evaluate_javascript(self, script: str, url: Optional[str] = None) -> str:
        if err := await self._ensure_url_visited(url, require_html=False):
            return err
        if self.state.current_url.startswith("search://"):
            return "Error: Cannot run JavaScript on search results. Visit a URL first."
        return await self.engine.run_javascript(self.state.current_url, script)

    async def screenshot(self, url: Optional[str] = None) -> Dict[str, str]:
        # Logic slightly different here: Screenshot can take a URL directly without state update if desired,
        # but for consistency, we'll hydrate state if a URL is passed.
        if url:
            await self.navigate(url)
        elif not self.state.current_url:
            return {
                "type": "text",
                "content": "Error: No URL provided and no page loaded.",
            }

        if self.state.current_url.startswith("search://"):
            return {
                "type": "text",
                "content": "Error: Cannot screenshot search results. Visit a URL first.",
            }

        b64 = await self.engine.take_screenshot(self.state.current_url)
        if not b64:
            return {"type": "text", "content": "Error: Screenshot failed."}
        return {"type": "image", "base64": b64, "content": "Screenshot captured."}

    # --- Navigation Helpers ---

    def scroll(self, direction: str = "down") -> str:
        # Scroll implies we are already looking at something, so strictly check state
        if err := self._validate_page_state(require_html=False):
            return err
        step = self.max_view_lines // 2
        if direction == "down":
            self.state.scroll_position += step
        else:
            self.state.scroll_position = max(0, self.state.scroll_position - step)
        return self._get_view_window()

    async def go_back(self) -> str:
        if self.state.history_index > 0:
            self.state.history_index -= 1
            prev_url = self.state.history[self.state.history_index]
            return await self._navigate_history(prev_url)
        return "Error: No history to go back to."

    async def go_forward(self) -> str:
        if self.state.history_index < len(self.state.history) - 1:
            self.state.history_index += 1
            next_url = self.state.history[self.state.history_index]
            return await self._navigate_history(next_url)
        return "Error: No forward history."

    # --- State Management & Validation ---

    async def _ensure_url_visited(
        self, url: Optional[str], require_html: bool
    ) -> Optional[str]:
        """
        Smart Validator:
        1. If URL provided, visits it (hydrating state).
        2. If no URL, checks if we already have state.
        3. If checks fail, returns Friendly Error Message.
        """
        if url:
            await self.navigate(url)
            # If after navigation we still don't have HTML (e.g. DNS error handled in navigate but returns error string),
            # we need to verify.
            if require_html and not self.state.current_html:
                return f"Error: Attempted to visit '{url}' but failed to retrieve valid HTML content."
            return None  # Success

        # Fallback to existing state check
        return self._validate_page_state(require_html)

    def _validate_page_state(self, require_html: bool = False) -> Optional[str]:
        if not self.state.current_url:
            return "Error: No URL provided and no page currently loaded. Please provide a 'url' argument or visit a page first."

        if require_html and not self.state.current_html:
            return "Error: This tool requires a full web page structure, but you are viewing search results. Please 'visit' a specific link first."

        return None

    async def _navigate_history(self, url: str) -> str:
        if url.startswith("search://"):
            query = url.replace("search://", "")
            markdown, interactables = await self.engine.search(query)
            self._set_page_content(url, markdown, interactables, "")
        else:
            markdown, title, interactables, raw_html = await self.engine.browse_url(url)
            self._set_page_content(
                url, f"# {title}\nURL: {url}\n\n{markdown}", interactables, raw_html
            )
        return self._get_view_window()

    def _set_page_content(
        self, url: str, markdown: str, interactables: Dict, raw_html: str
    ):
        self.state.current_url = url
        self.state.current_markdown = markdown
        self.state.current_interactables = interactables
        self.state.current_html = raw_html
        self.state.scroll_position = 0

    def _record_visit(self, url: str):
        if self.state.history_index < len(self.state.history) - 1:
            self.state.history = self.state.history[: self.state.history_index + 1]
        self.state.history.append(url)
        self.state.history_index = len(self.state.history) - 1

    def _get_view_window(self) -> str:
        lines = self.state.current_markdown.split("\n")
        total_lines = len(lines)
        start = self.state.scroll_position
        end = min(total_lines, start + self.max_view_lines)
        view_content = "\n".join(lines[start:end])
        footer = f"\n\n--- View: Lines {start}-{end} of {total_lines} ---"
        if end < total_lines:
            footer += "\n(Use 'scroll down' to see more)"
        return view_content + footer

    def get_tool_definition(self) -> list[dict]:
        # Helper to add 'url' property to inspection tools
        def add_url_param(params: dict):
            params["properties"]["url"] = {
                "type": "string",
                "description": "Optional: URL to visit before performing the action. Use this for one-shot execution.",
            }
            return params

        return [
            {
                "type": "function",
                "function": {
                    "name": "browser_search",
                    "description": "Search the web.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_visit",
                    "description": "Directly visit a URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_interact",
                    "description": "Interact with elements (Links, Buttons, Inputs) by ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["click", "type"]},
                            "id": {"type": "integer"},
                            "value": {
                                "type": "string",
                                "description": "Text to type (only for action='type')",
                            },
                        },
                        "required": ["action", "id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_scan",
                    "description": "Filter/Extract content using logic.",
                    "parameters": add_url_param(
                        {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "description": "String or JSON Logic",
                                    "anyOf": [{"type": "string"}, {"type": "object"}],
                                }
                            },
                            "required": ["query"],
                        }
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_screenshot",
                    "description": "Take visual screenshot.",
                    "parameters": add_url_param(
                        {"type": "object", "properties": {}, "required": []}
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_get_structure",
                    "description": "Get Table of Contents (Headers).",
                    "parameters": add_url_param(
                        {"type": "object", "properties": {}, "required": []}
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_get_links",
                    "description": "Get condensed list of links.",
                    "parameters": add_url_param(
                        {"type": "object", "properties": {}, "required": []}
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_get_main_content",
                    "description": "Get content stripped of clutter.",
                    "parameters": add_url_param(
                        {"type": "object", "properties": {}, "required": []}
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_run_javascript",
                    "description": "Run raw JavaScript.",
                    "parameters": add_url_param(
                        {
                            "type": "object",
                            "properties": {"script": {"type": "string"}},
                            "required": ["script"],
                        }
                    ),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_scroll",
                    "description": "Scroll view.",
                    "parameters": {
                        "type": "object",
                        "properties": {"direction": {"enum": ["up", "down"]}},
                        "required": ["direction"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_history",
                    "description": "Navigate history.",
                    "parameters": {
                        "type": "object",
                        "properties": {"action": {"enum": ["back", "forward"]}},
                        "required": ["action"],
                    },
                },
            },
        ]
