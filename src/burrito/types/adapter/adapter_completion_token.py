from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AdapterCompletionToken(BaseModel):
    created_at: float
    id: int
    text: str
    index: int
    finish_reason: Optional[str]
    is_special_token: bool
