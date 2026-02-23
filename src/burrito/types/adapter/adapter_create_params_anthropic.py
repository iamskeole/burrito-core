from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings


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


class AdapterInputParamMessageAnthropic(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]


class AdapterToolParamInputAnthropic(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None

    # compatibility with WebsearchToolParam
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    max_uses: Optional[int] = None


class WebSearchToolParamAnthropic(BaseModel):
    type: Literal["web_search_20250305", "web_search"] = "web_search"
    name: Literal["web_search"]
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    max_uses: Optional[int] = None

    # compatibility with ToolParam
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None


ToolInputParam = Union[AdapterToolParamInputAnthropic, WebSearchToolParamAnthropic]


class ToolChoiceAuto(BaseModel):
    type: Literal["auto"]


class ToolChoiceAny(BaseModel):
    type: Literal["any"]


class ToolChoiceTool(BaseModel):
    type: Literal["tool"]
    name: str


ToolChoice = Union[ToolChoiceAuto, ToolChoiceAny, ToolChoiceTool]


class Conversation(BaseModel):
    id: str


class AdapterReasoningParamAnthropic(BaseModel):
    budget_tokens: Optional[int] = 32000
    type: Optional[Literal["enabled"]] = "enabled"


class AdapterCreateParamsAnthropic(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    messages: List[AdapterInputParamMessageAnthropic]
    conversation: Optional[Conversation] = None
    system: Optional[Union[str, List[ContentBlockText]]] = None
    max_tokens: int = 4096
    metadata: Optional[Dict[str, Any]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = True
    prompt_cache_key: Optional[str] = None
    temperature: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0
    top_k: Optional[int] = None
    tools: Optional[List[ToolInputParam]] = None
    tool_choice: Optional[ToolChoice] = None
    thinking: Optional[AdapterReasoningParamAnthropic] = None
    model_config = ConfigDict(extra="allow")


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class AdapterMessageResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: List[ContentBlock]
    model: str
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: Usage
