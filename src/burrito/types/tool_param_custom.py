from typing import Annotated, Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, Field


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


class CustomToolDefinitionChat(BaseModel):
    name: str
    description: Optional[str] = None
    format: Optional[CustomToolInputFormat] = None


class ToolParamCustomChat(BaseModel):
    type: Literal["custom"]
    custom: CustomToolDefinitionChat


class ToolParamCustomResponses(BaseModel):
    name: str
    type: Literal["custom"]
    description: Optional[str] = None
    format: Optional[CustomToolInputFormat] = None


ToolParamCustom = Union[
    ToolParamCustomResponses,
    ToolParamCustomChat,
]
