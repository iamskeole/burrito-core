from typing import Literal, Optional, Union

from pydantic import BaseModel


class AdapterWebSearchToolParamChat(BaseModel):
    type: Literal["web_search"]
    web_search_enabled: Optional[bool] = True


class AdapterWebSearchToolParamResponses(BaseModel):
    type: Literal["web_search"]
    web_search_enabled: Optional[bool] = True


AdapterWebSearchToolParam = Union[
    AdapterWebSearchToolParamResponses,
    AdapterWebSearchToolParamChat,
]
