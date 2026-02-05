from typing import Literal, Optional, Union

from pydantic import BaseModel


class AdapterPythonToolParamChat(BaseModel):
    type: Literal["python", "code_interpreter"]
    backend: Optional[Literal["docker", "dangerously_use_local_jupyter"]] = "docker"


class AdapterPythonToolParamResponses(BaseModel):
    type: Literal["web_search", "browser_search"]
    backend: Optional[Literal["docker", "dangerously_use_local_jupyter"]] = "docker"


AdapterPythonToolParam = Union[
    AdapterPythonToolParamResponses,
    AdapterPythonToolParamChat,
]
