from __future__ import annotations

from enum import Enum


class AdapterConversationState(str, Enum):
    INITIAL = "initial"
    CREATED = "created"
    IN_PROGRESS = "in_progress"

    REASONING = "reasoning"
    REASONING_END = "reasoning_end"

    NATIVE_TOOL_INPUT_START = "native_tool_input"
    NATIVE_TOOL_INPUT = "native_tool_input"
    NATIVE_TOOL_CALL = "native_tool_call"

    TOOL_INPUT_START = "tool_input"
    TOOL_INPUT = "tool_input"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"  # not needed?

    OUTPUT_TEXT = "output_text"
    COMPLETED = "completed"
    TRANSITION = "transition"
    PREAMBLE = "preamble"
    ERROR = "error"

    @classmethod
    def _missing_(cls, value: object) -> "AdapterConversationState":  # type: ignore[override]
        raise ValueError(f"Unknown conversation state: {value!r}")
