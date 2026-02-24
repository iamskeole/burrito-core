from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from burrito.types.adapter import (
        AdapterCreateParamsAnthropic,
        AdapterCreateParamsChat,
        AdapterCreateParamsResponses,
    )

AdapterCreateParams = Union[
    "AdapterCreateParamsChat",
    "AdapterCreateParamsResponses",
    "AdapterCreateParamsAnthropic",
]
