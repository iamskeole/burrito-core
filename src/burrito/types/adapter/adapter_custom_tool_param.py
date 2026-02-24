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


class AdapterCustomToolDefinitionChat(BaseModel):
    name: str
    description: Optional[str] = None
    format: Optional[CustomToolInputFormat] = None


class AdapterCustomToolParamChat(BaseModel):
    type: Literal["custom"]
    custom: AdapterCustomToolDefinitionChat


class AdapterCustomToolParamResponses(BaseModel):
    name: str
    type: Literal["custom"]
    description: Optional[str] = None
    format: Optional[CustomToolInputFormat] = None


AdapterCustomToolParam = Union[
    AdapterCustomToolParamResponses,
    AdapterCustomToolParamChat,
]
