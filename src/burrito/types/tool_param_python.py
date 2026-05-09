from typing import Literal, Optional, Union

from pydantic import BaseModel


class ToolParamPythonChat(BaseModel):
    type: Literal["python", "code_interpreter"]


class ToolParamPythonResponses(BaseModel):
    type: Literal["python", "code_interpreter"]
    container: Optional["str"] = "not-implemented"


ToolParamPython = Union[
    ToolParamPythonResponses,
    ToolParamPythonChat,
]
