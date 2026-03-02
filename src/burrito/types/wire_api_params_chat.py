from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from burrito.types.conversation_enums import ConversationReasoningEffort
from burrito.types.tool_param_browser import ToolParamBrowserChat
from burrito.types.tool_param_function import ToolParamFunctionChat
from burrito.types.tool_param_python import ToolParamPythonChat

DEFAULT_REASONING_EFFORT = settings.DEFAULT_REASONING_EFFORT


class ContentPartText(BaseModel):
    type: Literal["text"]
    text: str


class ImageUrl(BaseModel):
    url: str
    detail: Optional[Literal["auto", "low", "high"]] = "auto"


class ContentPartImageUrl(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrl


class SystemMessageParam(BaseModel):
    role: Literal["system"]
    content: Union[str, List[ContentPartText]]
    name: Optional[str] = None


class DeveloperMessageParam(BaseModel):
    role: Literal["developer"]
    content: Union[str, List[ContentPartText]]
    name: Optional[str] = None


class UserMessageParam(BaseModel):
    role: Literal["user"]
    content: Union[str, List[Union[ContentPartText, ContentPartImageUrl]]]
    name: Optional[str] = None


class AssistantToolCallInputsParam(BaseModel):
    name: str
    arguments: str


class AssistantToolCallParam(BaseModel):
    id: str
    type: Literal["function", "custom_tool_call"]
    function: AssistantToolCallInputsParam


class AssistantMessageParam(BaseModel):
    role: Literal["assistant"]
    content: Optional[Union[str, List[ContentPartText]]] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[AssistantToolCallParam]] = None


class ToolCallOutputParam(BaseModel):
    content: str
    role: Literal["tool"]
    tool_call_id: str


InputItemParamChat = Annotated[
    Union[
        SystemMessageParam,
        DeveloperMessageParam,
        UserMessageParam,
        AssistantMessageParam,
        ToolCallOutputParam,
    ],
    Field(discriminator="role"),
]


class Conversation(BaseModel):
    id: str


class WireApiParamsChat(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    messages: List[InputItemParamChat]
    conversation: Optional[Conversation] = None
    reasoning_effort: Optional[str] = ConversationReasoningEffort(
        DEFAULT_REASONING_EFFORT
    )
    temperature: Optional[Annotated[float, Field(ge=-2.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    min_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 0.0
    top_k: Optional[Annotated[int, Field(ge=0, le=100)]] = 0
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    prompt_cache_key: Optional[str] = None

    tools: Optional[
        List[
            Annotated[
                Union[
                    ToolParamBrowserChat,
                    ToolParamPythonChat,
                    ToolParamFunctionChat,
                    # we disable custom tools as an input option
                    # to force schema validation failure
                    # see note in harmony_service for more details
                    # ToolParamCustomChat,
                ],
                Field(discriminator="type"),
            ]
        ]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    stream: Optional[bool] = False
    model_config = ConfigDict(extra="allow")
