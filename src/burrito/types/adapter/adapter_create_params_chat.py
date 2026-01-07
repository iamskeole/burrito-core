from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field

from .adapter_reasoning import AdapterReasoning


class FunctionDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]


class AdapterFunctionToolChat(BaseModel):
    type: Literal["function"]
    function: FunctionDefinition


class ContentPartText(BaseModel):
    type: Literal["text"]
    text: str


class ImageUrl(BaseModel):
    url: str
    detail: Optional[Literal["auto", "low", "high"]] = "auto"


class ContentPartImageUrl(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrl


class SystemMessage(BaseModel):
    role: Literal["system"]
    content: str
    name: Optional[str] = None


class DeveloperMessage(BaseModel):
    role: Literal["developer"]
    content: str
    name: Optional[str] = None


class UserMessage(BaseModel):
    role: Literal["user"]
    content: Union[str, List[Union[ContentPartText, ContentPartImageUrl]]]
    name: Optional[str] = None


class AdapterToolCallFunctionChat(BaseModel):
    name: str
    arguments: str


class AssistantToolCall(BaseModel):
    id: str
    type: Literal["function"]
    function: AdapterToolCallFunctionChat


class AssistantMessage(BaseModel):
    role: Literal["assistant"]
    content: Optional[str] = None
    tool_calls: Optional[List[AssistantToolCall]] = None


class AdapterToolMessageChat(BaseModel):
    role: Literal["tool"]
    content: str
    tool_call_id: str


ChatMessage = Annotated[
    Union[
        SystemMessage,
        DeveloperMessage,
        UserMessage,
        AssistantMessage,
        AdapterToolMessageChat,
    ],
    Field(discriminator="role"),
]


Reasoning: TypeAlias = AdapterReasoning


class AdapterCreateParamsChat(BaseModel):
    """
    Validates the request body for the POST /v1/chat/completions endpoint.
    """

    model: str
    messages: List[ChatMessage]

    reasoning: Optional[Reasoning] = None

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None

    tools: Optional[List[AdapterFunctionToolChat]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

    model_config = ConfigDict(
        extra="allow",
    )
