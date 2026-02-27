from __future__ import annotations

from typing import List, Literal, Optional

from openai_harmony import Message
from pydantic import BaseModel

from burrito.common.config import settings

from .conversation_enums import (
    ConversationReasoningEffort,
    ConversationReasoningSummary,
)
from .tool_param_custom import CustomToolInputFormat


class ConversationToolParam(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None
    strict: Optional[bool] = None
    format: Optional[CustomToolInputFormat] = None
    type: Literal["python", "browser", "function", "custom"] = "function"


class ConversationReasoningParam(BaseModel):
    effort: Optional[str] = ConversationReasoningEffort(
        settings.DEFAULT_REASONING_EFFORT
    )
    summary: Optional[str] = ConversationReasoningSummary(
        settings.DEFAULT_REASONING_SUMMARY
    )


class ConversationInputs(BaseModel):
    instructions: Optional[str] | None = None
    messages: List[Message]
    tools: Optional[List[ConversationToolParam]]
    reasoning: Optional[ConversationReasoningParam]
