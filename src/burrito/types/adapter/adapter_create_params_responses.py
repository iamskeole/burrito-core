from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from burrito.types.adapter.adapter_reasoning import AdapterReasoningParam
from burrito.types.adapter.adapter_function_tool_param import (
    AdapterFunctionToolParamResponses,
)
from burrito.types.adapter.adapter_browser_tool_param import (
    AdapterBrowserToolParamResponses,
)
from burrito.types.adapter.adapter_python_tool_param import (
    AdapterPythonToolParamResponses,
)
# TODO: investiagate whether we can support custom tools
# harmony only seems to support defining regular function tools
# with name, description, params; no special formatting instructions
# for custom tools, so even if we implemented schemas and code, model
# may not be trained to use them?
# so we disable that option as an input to force schema validation failure
# from .adapter_custom_tool_param import AdapterCustomToolParamResponses


class InputTextParamResponses(BaseModel):
    type: Literal["input_text"]
    text: str


class InputImageParamResponses(BaseModel):
    type: Literal["input_image"]
    image_url: str


ContentPartInputText = Annotated[
    Union[InputTextParamResponses, InputImageParamResponses],
    Field(discriminator="type"),
]


class ContentPartOutputTextParamResponses(BaseModel):
    type: Literal["output_text"]
    text: str
    annotations: Optional[List[Any]] = None


class BaseInputMessageParamResponses(BaseModel):
    type: Literal["message"] = "message"
    content: Union[
        str,
        List[
            Annotated[
                Union[
                    InputTextParamResponses,
                    InputImageParamResponses,
                ],
                Field(discriminator="type"),
            ],
        ],
    ]


class UserInputMessageParamResponses(BaseInputMessageParamResponses):
    role: Literal["user"]


class DeveloperInputMessageParamResponses(BaseInputMessageParamResponses):
    role: Literal["developer"]


class SystemInputMessageParamResponses(BaseInputMessageParamResponses):
    role: Literal["system"]


EasyInputParamResponses = Annotated[
    Union[
        UserInputMessageParamResponses,
        DeveloperInputMessageParamResponses,
        SystemInputMessageParamResponses,
    ],
    Field(discriminator="role"),
]


class AssistantReasoningContent(BaseModel):
    type: Literal["reasoning_text"]
    text: str


class AssistantReasoningParamResponses(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    summary: List[Any]
    content: List[AssistantReasoningContent]


class AssistantMessageContentParamResponses(BaseModel):
    type: Literal["message"]
    text: str


class AssistantMessageParamResponses(BaseModel):
    type: Literal["message"] = "message"
    role: Literal["assistant"]
    content: Union[str, List[ContentPartOutputTextParamResponses]]


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


ToolCallInputParamResponses = Annotated[
    Union[FunctionToolInputParamResponses, CustomToolInputParamResponses],
    Field(discriminator="type"),
]


class WebSearchCallOutputParamResponses(BaseModel):
    type: Literal["web_search_call"]
    status: Literal["in_progress", "searching", "completed"]
    action: Optional[Dict[str, Any]] = None


InputItemParamResponses = Union[
    EasyInputParamResponses,
    AssistantMessageParamResponses,
    AssistantReasoningParamResponses,
    ToolCallInputParamResponses,
    ToolCallOutputParamResponses,
    CustomToolCallOutputParamResponses,
    WebSearchCallOutputParamResponses,  # TODO: finish plugin implementation + code interpreter
]


class Conversation(BaseModel):
    id: str


class AdapterCreateParamsResponses(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    input: Union[str, List[InputItemParamResponses]]
    instructions: Optional[str] = None
    conversation: Optional[Conversation] = None

    reasoning: Optional[AdapterReasoningParam] = None

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = 1.0
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = 1.0

    max_output_tokens: Optional[int] = None
    prompt_cache_key: Optional[str] = None

    tools: Optional[
        List[
            Union[
                AdapterBrowserToolParamResponses,
                AdapterPythonToolParamResponses,
                AdapterFunctionToolParamResponses,
                # AdapterCustomToolParamChat, # see todo note above
            ]
        ]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"
    stream: Optional[bool] = True

    model_config = ConfigDict(extra="allow")
