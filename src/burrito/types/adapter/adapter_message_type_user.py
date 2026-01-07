from __future__ import annotations

from enum import Enum


class AdapterMessageTypeUser(str, Enum):
    TEXT = "text"
    INPUT_TEXT = "input_text"
