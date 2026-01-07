import logging
from typing import Dict, Optional, Any
from playwright.async_api import async_playwright, Browser

from burrito.services.browser.browser_engine import BrowserEngine
from burrito.services.browser.browser_tool import BrowserTool

logger = logging.getLogger(__name__)

class BrowserHandler:
    """
    Singleton handler that manages the Playwright process lifecycle
    and holds stateful browser sessions for users.
    Acts as a Facade for the BrowserTool.
    """
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._user_sessions: Dict[str, BrowserTool] = {}

    async def start(self):
        """Called by FastAPI Lifespan on startup"""
        if self._playwright is None:
            logger.info("Initializing Playwright Browser Handler...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            # Inject the global browser instance into the Engine class 
            BrowserEngine._playwright = self._playwright
            BrowserEngine._browser = self._browser

    async def stop(self):
        """Called by FastAPI Lifespan on shutdown"""
        logger.info("Shutting down Browser Handler...")
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._user_sessions.clear()

    def get_tool_for_user(self, user_id: str) -> BrowserTool:
        """
        Retrieves or creates a session for a specific user.
        """
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = BrowserTool()
        return self._user_sessions[user_id]
        
    def clear_user_session(self, user_id: str):
        if user_id in self._user_sessions:
            del self._user_sessions[user_id]

    async def perform_action(self, user_id: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Facade method: Retrieves the user's session and executes the requested action via Dispatcher.
        """
        tool = self.get_tool_for_user(user_id)
        return await tool.execute(action, params)