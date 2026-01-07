from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from .adapter_reasoning import AdapterReasoning


class CustomToolInputFormatText(BaseModel):
    type: Literal["text"]


class CustomToolInputFormatGrammar(BaseModel):
    definition: str
    syntax: Literal["lark", "regex"]
    type: Literal["grammar"]


CustomToolInputFormat: TypeAlias = Annotated[
    Union[CustomToolInputFormatText, CustomToolInputFormatGrammar],
    Field(discriminator="type"),
]


class AdapterCustomToolResponses(BaseModel):
    name: str
    type: Literal["custom"]
    description: Optional[str] = None
    format: Optional[CustomToolInputFormat] = None


class AdapterFunctionToolResponses(BaseModel):
    type: Literal["function"]
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    strict: Optional[bool] = False


class UserMessageContentText(BaseModel):
    type: Literal["input_text"]
    text: str


class UserMessageContentImage(BaseModel):
    type: Literal["input_image"]
    image_url: str


ContentPartInputText = Annotated[
    Union[UserMessageContentText, UserMessageContentImage], Field(discriminator="type")
]


class ContentPartOutputText(BaseModel):
    type: Literal["output_text"]
    text: str
    annotations: Optional[List[Any]] = None


class UserMessage(BaseModel):
    type: Literal["message"]
    role: Literal["user"]
    content: Union[
        str,
        List[
            Annotated[
                Union[UserMessageContentText, UserMessageContentText],
                Field(discriminator="type"),
            ],
        ],
    ]


class AssistantReasoningContent(BaseModel):
    type: Literal["reasoning_text"]
    text: str


class AssistantReasoning(BaseModel):
    type: Literal["reasoning"]
    summary: List[Any]
    content: List[AssistantReasoningContent]


class AssistantMessageContent(BaseModel):
    type: Literal["message"]
    text: str


class AssistantMessage(BaseModel):
    type: Literal["message"]
    role: Literal["assistant"]
    content: List[ContentPartOutputText]


class CustomToolCallOutput(BaseModel):
    type: Literal["custom_tool_call_output"]
    call_id: str
    output: str


class CustomToolCall(BaseModel):
    type: Literal["custom_tool_call"]
    call_id: str
    name: str
    input: str


class FunctionToolCallOutput(BaseModel):
    type: Literal["function_call_output"]
    call_id: str
    output: str


class FunctionToolCall(BaseModel):
    type: Literal["function_call"]
    name: str
    arguments: str
    call_id: str


ToolCallOutputItem = Annotated[
    Union[FunctionToolCallOutput, CustomToolCallOutput], Field(discriminator="type")
]

ToolCallItem = Annotated[
    Union[FunctionToolCall, CustomToolCall], Field(discriminator="type")
]


InputItem = Union[
    UserMessage,
    AssistantMessage,
    AssistantReasoning,
    ToolCallItem,
    ToolCallOutputItem,
]


Reasoning: TypeAlias = AdapterReasoning


class AdapterCreateParamsResponses(BaseModel):
    """
    Validates the request body for the POST /v1/responses endpoint.
    Handles the doubly-discriminated union for the `input` array.
    """

    model: Literal[settings.DEFAULT_MODEL_NAME]
    input: Union[str, List[InputItem]]

    reasoning: Optional[Reasoning] = None

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0

    instructions: Optional[str] = None
    tools: Optional[
        List[Union[AdapterFunctionToolResponses, AdapterCustomToolResponses]]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"
    stream: Optional[bool] = True

    model_config = ConfigDict(extra="allow")
