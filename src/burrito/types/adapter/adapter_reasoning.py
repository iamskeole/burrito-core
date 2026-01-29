from enum import Enum
from typing import Optional

from pydantic import BaseModel

from burrito.common.config import settings


class ReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningSummary(str, Enum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"


class AdapterReasoningParam(BaseModel):
    effort: Optional[ReasoningEffort] = ReasoningEffort(
        settings.DEFAULT_REASONING_EFFORT
    )
    summary: Optional[ReasoningSummary] = ReasoningSummary(
        settings.DEFAULT_REASONING_SUMMARY
    )
