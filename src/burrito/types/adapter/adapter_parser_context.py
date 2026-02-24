from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from burrito.types.adapter import AdapterCompletionToken


class AdapterParserContext(BaseModel):
    channel: Optional[str]
    recipient: Optional[str]
    last_token: AdapterCompletionToken
    response_tokens: List[AdapterCompletionToken]
    parser_state: str
