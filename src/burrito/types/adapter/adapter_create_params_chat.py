from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings

from .adapter_reasoning import ReasoningEffort
from .adapter_function_tool_param import AdapterFunctionToolParamChat
from .adapter_web_search_tool_param import AdapterWebSearchToolParamChat

# TODO: investiagate whether we can support custom tools
# harmony only seems to support defining regular function tools
# with name, description, params; no special formatting instructions
# for custom tools, so even if we implemented schemas and code, model
# may not be trained to use them?
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
    content: str
    name: Optional[str] = None


class DeveloperMessageParamChat(BaseModel):
    role: Literal["developer"]
    content: str
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
    content: Optional[str] = None
    tool_calls: Optional[List[AssistantToolCallParamChat]] = None


class ToolCallOutputParamChat(BaseModel):
    role: Literal["tool"]
    content: str
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


class AdapterCreateParamsChat(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    messages: List[InputItemParamChat]

    reasoning_effort: Optional[ReasoningEffort] = ReasoningEffort(
        settings.DEFAULT_REASONING_EFFORT
    )

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None

    tools: Optional[
        List[
            Annotated[
                Union[
                    AdapterFunctionToolParamChat,
                    AdapterWebSearchToolParamChat,
                    # disable custom tools, harmony only seems to support
                    # defining regular function tools with name, description, params
                    # no special formatting instructions for custom tools, so moot?
                    # AdapterCustomToolParamChat
                ],
                Field(discriminator="type"),
            ]
        ]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

    model_config = ConfigDict(extra="allow")
