from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel

from burrito.common.config import settings

DEFAULT_REASONING_EFFORT = settings.DEFAULT_REASONING_EFFORT
DEFAULT_REASONING_SUMMARY = settings.DEFAULT_REASONING_SUMMARY


class ReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ReasoningSummary = Literal["auto", "concise", "detailed"]


class AdapterReasoning(BaseModel):
    effort: Optional[ReasoningEffort] = ReasoningEffort(DEFAULT_REASONING_EFFORT)
    summary: Optional[ReasoningSummary] = DEFAULT_REASONING_SUMMARY
