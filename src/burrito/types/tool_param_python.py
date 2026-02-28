from typing import Literal, Optional, Union

from pydantic import BaseModel


class ToolParamPythonChat(BaseModel):
    type: Literal["python", "code_interpreter"]
    backend: Optional[Literal["docker", "dangerously_use_local_jupyter"]] = "docker"


class ToolParamPythonResponses(BaseModel):
    type: Literal["python", "code_interpreter"]
    backend: Optional[Literal["docker", "dangerously_use_local_jupyter"]] = "docker"


ToolParamPython = Union[
    ToolParamPythonResponses,
    ToolParamPythonChat,
]
