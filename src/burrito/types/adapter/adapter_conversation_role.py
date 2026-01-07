from __future__ import annotations

from enum import Enum


class AdapterConversationRole(Enum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
