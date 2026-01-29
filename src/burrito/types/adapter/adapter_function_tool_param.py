from typing import Literal, Optional, Dict, Any, Union

from pydantic import BaseModel


class AdapterFunctionToolDefinitionChat(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    strict: Optional[bool] = False


class AdapterFunctionToolParamChat(BaseModel):
    type: Literal["function"]
    function: AdapterFunctionToolDefinitionChat


class AdapterFunctionToolParamResponses(BaseModel):
    type: Literal["function"]
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    strict: Optional[bool] = False


AdapterFunctionToolParam = Union[
    AdapterFunctionToolParamResponses, AdapterFunctionToolParamChat
]
