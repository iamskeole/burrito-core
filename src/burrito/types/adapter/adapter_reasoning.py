from enum import Enum
from typing import Optional

from pydantic import BaseModel

from burrito.common.config import settings


class AdapterReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AdapterReasoningSummary(str, Enum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"


class AdapterReasoningParam(BaseModel):
    effort: Optional[AdapterReasoningEffort] = AdapterReasoningEffort(
        settings.DEFAULT_REASONING_EFFORT
    )
    summary: Optional[AdapterReasoningSummary] = AdapterReasoningSummary(
        settings.DEFAULT_REASONING_SUMMARY
    )
