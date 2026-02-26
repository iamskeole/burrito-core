from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel


# TODO: no anthropic?
class FunctionToolDefinitionChat(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    strict: Optional[bool] = False


class ToolParamFunctionChat(BaseModel):
    type: Literal["function"]
    function: FunctionToolDefinitionChat


class ToolParamFunctionResponses(BaseModel):
    type: Literal["function"]
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    strict: Optional[bool] = False


ToolParamFunction = Union[ToolParamFunctionResponses, ToolParamFunctionChat]
