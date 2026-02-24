from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from burrito.types.adapter.adapter_browser_tool_param import (
    AdapterBrowserToolParamChat,
)
from burrito.types.adapter.adapter_function_tool_param import (
    AdapterFunctionToolParamChat,
)
from burrito.types.adapter.adapter_python_tool_param import AdapterPythonToolParamChat
from burrito.types.adapter.adapter_reasoning import AdapterReasoningEffort

# tbd if custom tools can be supported
# from .adapter_custom_tool_param import AdapterCustomToolParamChat


class ContentPartText(BaseModel):
    type: Literal["text"]
    text: str


class ImageUrl(BaseModel):
    url: str
    detail: Optional[Literal["auto", "low", "high"]] = "auto"


class ContentPartImageUrl(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrl


class SystemMessageParamChat(BaseModel):
    role: Literal["system"]
    content: Union[str, List[ContentPartText]]
    name: Optional[str] = None


class DeveloperMessageParamChat(BaseModel):
    role: Literal["developer"]
    content: Union[str, List[ContentPartText]]
    name: Optional[str] = None


class UserMessageParamChat(BaseModel):
    role: Literal["user"]
    content: Union[str, List[Union[ContentPartText, ContentPartImageUrl]]]
    name: Optional[str] = None


class AssistantToolCallInputsParamChat(BaseModel):
    name: str
    arguments: str


class AssistantToolCallParamChat(BaseModel):
    id: str
    type: Literal["function", "custom_tool_call"]
    function: AssistantToolCallInputsParamChat


class AssistantMessageParamChat(BaseModel):
    role: Literal["assistant"]
    content: Optional[Union[str, List[ContentPartText]]] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[AssistantToolCallParamChat]] = None


class ToolCallOutputParamChat(BaseModel):
    content: str
    role: Literal["tool"]
    tool_call_id: str


InputItemParamChat = Annotated[
    Union[
        SystemMessageParamChat,
        DeveloperMessageParamChat,
        UserMessageParamChat,
        AssistantMessageParamChat,
        ToolCallOutputParamChat,
    ],
    Field(discriminator="role"),
]


class Conversation(BaseModel):
    id: str


class AdapterCreateParamsChat(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    messages: List[InputItemParamChat]
    conversation: Optional[Conversation] = None

    reasoning_effort: Optional[AdapterReasoningEffort] = AdapterReasoningEffort(
        settings.DEFAULT_REASONING_EFFORT
    )

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None

    prompt_cache_key: Optional[str] = None

    tools: Optional[
        List[
            Annotated[
                Union[
                    AdapterBrowserToolParamChat,
                    AdapterPythonToolParamChat,
                    AdapterFunctionToolParamChat,
                    # AdapterCustomToolParamChat, # see todo note above
                ],
                Field(discriminator="type"),
            ]
        ]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

    stream: Optional[bool] = False

    model_config = ConfigDict(extra="allow")
