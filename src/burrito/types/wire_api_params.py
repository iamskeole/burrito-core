from typing import Union

from burrito.types.wire_api_params_chat import WireApiParamsChat
from burrito.types.wire_api_params_messages import WireApiParamsMessages
from burrito.types.wire_api_params_responses import WireApiParamsResponses

WireApiParams = Union[
    "WireApiParamsChat",
    "WireApiParamsResponses",
    "WireApiParamsMessages",
]
