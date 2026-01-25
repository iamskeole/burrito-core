from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel


class BrowserResponseMetadata(BaseModel):
    title: Optional[str] | None = None
    description: Optional[str] | None = None
    author: Optional[str] | None = None
    url: Optional[str] | None = None
    hostname: Optional[str] | None = None
    sitename: Optional[str] | None = None
    date: Optional[str] | None = None
    filedate: Optional[str] | None = None
    tags: Optional[List[str]] | None = None
    pagetype: Optional[str] | None = None


class BrowserResponseFetch(BaseModel):
    text: str
    metadata: BrowserResponseMetadata
