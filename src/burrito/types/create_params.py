from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    pass
    # from burrito.types import (
    #     CreateParamsChat,
    #     CreateParamsMessages,
    #     CreateParamsResponses,
    # )

from burrito.types.create_params_chat import CreateParamsChat
from burrito.types.create_params_messages import CreateParamsMessages
from burrito.types.create_params_responses import CreateParamsResponses

CreateParams = Union[
    "CreateParamsChat",
    "CreateParamsResponses",
    "CreateParamsMessages",
]
