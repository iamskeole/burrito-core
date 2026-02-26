from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from burrito.types.tool_param_browser import ToolParamBrowserMessages


class ContentBlockText(BaseModel):
    type: Literal["text"]
    text: str


class ContentBlockImage(BaseModel):
    type: Literal["image"]
    source: Dict[str, Any]


class ContentBlockToolUse(BaseModel):
    type: Literal["tool_use", "server_tool_use"]
    id: str
    name: str
    input: Union[str, Dict[str, Any]]
    caller: Optional[str] = None


class ContentBlockToolResult(BaseModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Optional[Union[str, List[Union[ContentBlockText, ContentBlockImage]]]] = (
        None
    )
    is_error: Optional[bool] = False


class ContentBlockAssistantReasoning(BaseModel):
    type: Literal["thinking"]
    signature: Optional[str] = None
    thinking: Optional[str] = None


ContentBlock = Annotated[
    Union[
        ContentBlockText,
        ContentBlockImage,
        ContentBlockToolUse,
        ContentBlockToolResult,
        ContentBlockAssistantReasoning,
    ],
    Field(discriminator="type"),
]


class ContentParam(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]


class ToolParam(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None

    # compatibility with WebsearchToolParam
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    max_uses: Optional[int] = None


ToolInputParam = Union[ToolParam, ToolParamBrowserMessages]


class ToolChoiceAuto(BaseModel):
    type: Literal["auto"]


class ToolChoiceAny(BaseModel):
    type: Literal["any"]


class ToolChoiceTool(BaseModel):
    type: Literal["tool"]
    name: str


ToolChoice = Union[ToolChoiceAuto, ToolChoiceAny, ToolChoiceTool]


class ConversationParam(BaseModel):
    id: str


class ReasoningParam(BaseModel):
    budget_tokens: Optional[int] = 32000
    type: Optional[Literal["enabled"]] = "enabled"


class CreateParamsMessages(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    messages: List[ContentParam]
    conversation: Optional[ConversationParam] = None
    system: Optional[Union[str, List[ContentBlockText]]] = None
    max_tokens: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = True
    prompt_cache_key: Optional[str] = None
    temperature: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    top_k: Optional[int] = None
    tools: Optional[List[ToolInputParam]] = None
    tool_choice: Optional[ToolChoice] = None
    thinking: Optional[ReasoningParam] = None
    model_config = ConfigDict(extra="allow")
