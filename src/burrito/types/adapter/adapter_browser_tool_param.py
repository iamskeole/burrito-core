from typing import Literal, Optional, Union

from pydantic import BaseModel


class AdapterBrowserToolParamChat(BaseModel):
    type: Literal["web_search", "browser_search"]
    web_search_enabled: Optional[bool] = True


class AdapterBrowserToolParamResponses(BaseModel):
    type: Literal["web_search", "browser_search"]
    web_search_enabled: Optional[bool] = True


AdapterBrowserToolParam = Union[
    AdapterBrowserToolParamResponses,
    AdapterBrowserToolParamChat,
]
