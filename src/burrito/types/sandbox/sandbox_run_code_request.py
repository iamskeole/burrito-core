from typing import List, Optional

from pydantic import BaseModel


class SandboxRequest(BaseModel):
    session_id: str
    code: str
    replay: bool = True
    previous: Optional[List[str]] = None


class SandboxResponse(BaseModel):
    stdout: str
    stderr: str