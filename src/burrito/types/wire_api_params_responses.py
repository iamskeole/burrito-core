from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from burrito.common.config import settings
from burrito.types.conversation_inputs import ConversationReasoningParam
from burrito.types.tool_param_browser import ToolParamBrowserResponses
from burrito.types.tool_param_custom import ToolParamCustomResponses
from burrito.types.tool_param_function import ToolParamFunctionResponses
from burrito.types.tool_param_python import ToolParamPythonResponses


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
    WebSearchCallOutputParamResponses,
]


class Conversation(BaseModel):
    id: str


class WireApiParamsResponses(BaseModel):
    model: str = settings.DEFAULT_MODEL_NAME
    input: Union[str, List[InputItemParamResponses]]
    instructions: Optional[str] = None
    conversation: Optional[Conversation] = None

    reasoning: Optional[ConversationReasoningParam] = None

    top_k: Optional[Annotated[int, Field(ge=0, le=100)]] = (
        settings.SAMPLING_DEFAULT_TOP_K
    )
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = (
        settings.SAMPLING_DEFAULT_TOP_P
    )
    min_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = (
        settings.SAMPLING_DEFAULT_MIN_P
    )
    temperature: Optional[Annotated[float, Field(ge=-2.0, le=2.0)]] = (
        settings.SAMPLING_DEFAULT_TEMPERATURE
    )
    seed: Optional[Annotated[int, Field(ge=0)]] = settings.SAMPLING_DEFAULT_SEED

    max_output_tokens: Optional[int] = None
    prompt_cache_key: Optional[str] = None

    tools: Optional[
        List[
            Union[
                ToolParamBrowserResponses,
                ToolParamPythonResponses,
                ToolParamFunctionResponses,
                # we disable custom tools as an input option
                # to force schema validation failure
                # see note in harmony_service for more details
                ToolParamCustomResponses,
            ]
        ]
    ] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"
    stream: Optional[bool] = False

    model_config = ConfigDict(extra="allow")
