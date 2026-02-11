import hashlib

from typing import Dict, Optional, List

from burrito.tools.python.tool import BurritoPython
from burrito.tools.browser.tool import BurritoBrowser


class AdapterSessionHandler:
    def __init__(self):
        self.python_tools: Dict[str, Optional[BurritoPython]] = {}
        self.browser_tools: Dict[str, Optional[BurritoBrowser]] = {}

    @staticmethod
    def int_to_bytes(n: int) -> bytes:
        return n.to_bytes((n.bit_length() + 7) // 8, "big", signed=False)

    def hash_text(self, prompt: str):
        return hashlib.sha256(prompt.encode()).digest().hex()

    def hash_tokens(self, prompt_tokens: List[int]):
        n = sum(prompt_tokens)
        return hashlib.sha256(self.int_to_bytes(n)).digest().hex()

    def set_python_tool(self, session_id: str, tool: Optional[BurritoPython]) -> None:
        if session_id not in self.python_tools:
            self.python_tools[session_id] = tool

    def set_browser_tool(self, session_id: str, tool: Optional[BurritoBrowser]) -> None:
        if session_id not in self.browser_tools:
            self.browser_tools[session_id] = tool

    def get_python_tool(self, session_id: str) -> Optional[BurritoPython]:
        return self.python_tools.get(session_id)

    def get_browser_tool(self, session_id: str) -> Optional[BurritoBrowser]:
        return self.browser_tools.get(session_id)
