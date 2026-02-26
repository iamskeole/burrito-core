from typing import Literal, Optional

from pydantic import BaseModel


class StreamError(BaseModel):
    type: Literal["error"]
    code: str
    message: str
    param: Optional[str] = None
    sequence_number: int
