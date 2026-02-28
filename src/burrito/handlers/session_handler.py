import hashlib
import uuid
from typing import Optional

from burrito.common.config import settings
from burrito.common.utils import LruDict
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython


class SessionHandler:
    def __init__(self):
        maxsize = settings.BROWSER_SESSION_CACHE_SIZE
        self.python_tools: LruDict[str, Optional[BurritoPython]] = LruDict(maxsize)
        self.browser_tools: LruDict[str, Optional[BurritoBrowser]] = LruDict(maxsize)

    def hash_prompt(self, prompt: str) -> str:
        hash_bytes = hashlib.sha256(prompt.encode()).digest()
        return str(uuid.UUID(bytes=hash_bytes[:16]))

    def set_python_tool(self, session_id: str, tool: Optional[BurritoPython]) -> None:
        if session_id in self.python_tools:
            return
        self.python_tools[session_id] = tool

    def set_browser_tool(self, session_id: str, tool: Optional[BurritoBrowser]) -> None:
        if session_id in self.browser_tools:
            return
        self.browser_tools[session_id] = tool

    def get_python_tool(self, session_id: str) -> Optional[BurritoPython]:
        return self.python_tools.get(session_id)

    def get_browser_tool(self, session_id: str) -> Optional[BurritoBrowser]:
        return self.browser_tools.get(session_id)
