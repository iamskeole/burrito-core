import hashlib
import struct
import uuid
from typing import Dict, List, Optional

from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython


class AdapterSessionHandler:
    def __init__(self):
        self.python_tools: Dict[str, Optional[BurritoPython]] = {}
        self.browser_tools: Dict[str, Optional[BurritoBrowser]] = {}

    @staticmethod
    def int_to_bytes(n: int) -> bytes:
        return n.to_bytes((n.bit_length() + 7) // 8, "big", signed=False)

    def bytes_to_uuid(self, _bytes: bytes) -> str:
        return str(uuid.UUID(bytes=_bytes[:16]))

    def hash_text(self, prompt: str) -> str:
        hash_bytes = hashlib.sha256(prompt.encode()).digest()
        return self.bytes_to_uuid(hash_bytes)

    def hash_tokens(self, prompt_tokens: List[int]):
        token_bytes = struct.pack(f"<{len(prompt_tokens)}I", *prompt_tokens)
        hash_bytes = hashlib.sha256(token_bytes).digest()
        return self.bytes_to_uuid(hash_bytes)

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
