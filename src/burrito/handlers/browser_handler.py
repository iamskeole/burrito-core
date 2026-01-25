import logging
from typing import Dict, Optional, Any
from playwright.async_api import async_playwright, Browser

from burrito.tools.browser.engine import BrowserEngine
from burrito.tools.browser.tool import BrowserTool

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
        logger.info("Initializing Browser Engine...")
        await BrowserEngine.start()

    async def stop(self):
        """Called by FastAPI Lifespan on shutdown"""
        logger.info("Shutting down Browser Engine...")
        await BrowserEngine.stop()
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