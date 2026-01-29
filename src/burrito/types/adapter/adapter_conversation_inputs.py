from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypeAlias

from openai_harmony import Message
from pydantic import BaseModel

from .adapter_custom_tool_param import CustomToolInputFormat
from .adapter_reasoning import AdapterReasoningParam


class AdapterConversationInputMessageContent(BaseModel):
    text: str
    type: str


class AdapterConversationInputMessage(BaseModel):
    type: Literal[
        "reasoning",
        "message",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
    ]
    role: Literal["user", "assistant", "tool"]
    content: List[AdapterConversationInputMessageContent]


class AdapterConversationInputToolParam(BaseModel):
    type: str
    properties: Dict
    required: List[str]
    additionalProperties: bool


class AdapterConversationInputTool(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None
    strict: Optional[bool] = None
    format: Optional[CustomToolInputFormat] = None
    type: Literal["python", "browser", "function", "custom"] = "function"


class AdapterConversationInputs(BaseModel):
    instructions: Optional[str] | None = None
    messages: List[Message]
    tools: Optional[List[AdapterConversationInputTool]]
    reasoning: Optional[AdapterReasoningParam]
