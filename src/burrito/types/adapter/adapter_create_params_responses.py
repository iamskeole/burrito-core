from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from .adapter_reasoning import AdapterReasoningParam
from .adapter_function_tool_param import AdapterFunctionToolParam
from .adapter_custom_tool_param import AdapterCustomToolParam


class UserMessageContentTextParamResponses(BaseModel):
    type: Literal["input_text"]
    text: str


class UserMessageContentImageParamResponses(BaseModel):
    type: Literal["input_image"]
    image_url: str


ContentPartInputText = Annotated[
    Union[UserMessageContentTextParamResponses, UserMessageContentImageParamResponses],
    Field(discriminator="type"),
]


class ContentPartOutputTextParamResponses(BaseModel):
    type: Literal["output_text"]
    text: str
    annotations: Optional[List[Any]] = None


class UserMessageParamResponses(BaseModel):
    type: Literal["message"]
    role: Literal["user", "developer"]
    content: Union[
        str,
        List[
            Annotated[
                Union[
                    UserMessageContentTextParamResponses,
                    UserMessageContentImageParamResponses,
                ],
                Field(discriminator="type"),
            ],
        ],
    ]


class AssistantReasoningContent(BaseModel):
    type: Literal["reasoning_text"]
    text: str


class AssistantReasoningParamResponses(BaseModel):
    type: Literal["reasoning"]
    summary: List[Any]
    content: List[AssistantReasoningContent]


class AssistantMessageContentParamResponses(BaseModel):
    type: Literal["message"]
    text: str


class AssistantMessageParamResponses(BaseModel):
    type: Literal["message"]
    role: Literal["assistant"]
    content: List[ContentPartOutputTextParamResponses]


class CustomToolCallOutputParamResponses(BaseModel):
    type: Literal["custom_tool_call_output"]
    call_id: str
    output: str


class CustomToolInputParamResponses(BaseModel):
    type: Literal["custom_tool_call"]
    call_id: str
    name: str
    input: str


class ToolCallOutputParamResponses(BaseModel):
    type: Literal["function_call_output"]
    call_id: str
    output: str


class FunctionToolInputParamResponses(BaseModel):
    type: Literal["function_call"]
    name: str
    arguments: str
    call_id: str


ToolCallOutputParamResponses = Annotated[
    Union[ToolCallOutputParamResponses, CustomToolCallOutputParamResponses],
    Field(discriminator="type"),
]

ToolCallInputParamResponses = Annotated[
    Union[FunctionToolInputParamResponses, CustomToolInputParamResponses],
    Field(discriminator="type"),
]


InputItemParamResponses = Union[
    UserMessageParamResponses,
    AssistantMessageParamResponses,
    AssistantReasoningParamResponses,
    ToolCallInputParamResponses,
    ToolCallOutputParamResponses,
]


class AdapterCreateParamsResponses(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    input: Union[str, List[InputItemParamResponses]]

    reasoning: Optional[AdapterReasoningParam] = None

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0

    instructions: Optional[str] = None
    tools: Optional[
        List[
            Union[
                AdapterFunctionToolParam,
                AdapterCustomToolParam,
            ]
        ]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"
    stream: Optional[bool] = True

    model_config = ConfigDict(extra="allow")
