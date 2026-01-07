from __future__ import annotations

from enum import Enum


class AdapterRequestCategory(str, Enum):
    CHAT = "chat"
    RESPONSES = "responses"
    EMBEDDINGS = "embeddings"
