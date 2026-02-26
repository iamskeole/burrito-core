from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel


class ToolParamBrowserChat(BaseModel):
    type: Literal["web_search", "browser_search"]
    web_search_enabled: Optional[bool] = True


class ToolParamBrowserResponses(BaseModel):
    type: Literal["web_search", "browser_search"]
    web_search_enabled: Optional[bool] = True


class ToolParamBrowserMessages(BaseModel):
    type: Literal["web_search_20250305", "web_search"] = "web_search"
    name: Literal["web_search"]
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    max_uses: Optional[int] = None

    # compatibility with ToolParam
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None


ToolParamBrowser = Union[
    ToolParamBrowserResponses,
    ToolParamBrowserChat,
    ToolParamBrowserMessages,
]
