import json
from typing import TYPE_CHECKING, Optional

from openai.types.responses.response import Response
from openai.types.responses.response_output_item import ResponseOutputItem
from pydantic import BaseModel

from burrito.common.utils import random_uuid, unix_timestamp
from burrito.types.adapter import AdapterConversationState

from ..base_plugin import BasePlugin

if TYPE_CHECKING:
    from burrito.adapter.handlers.state_handler import (
        AdapterStateHandler,
    )


class BasePluginResponses(BasePlugin):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.log_extra = {"log_id": f"apr_{self.log_id}"}

    def init_response_object(self) -> Response:
        params = self.manager.manager.params.model_dump()
        init_data = {
            "id": f"resp_{random_uuid()}",
            "created_at": unix_timestamp(),
            "object": "response",
            "output": [],
            "status": AdapterConversationState.IN_PROGRESS.value,  # type: ignore
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
        }
        for k, v in params.items():
            if not v:
                continue
            # if k not in init_data:
            #     continue
            init_data[k] = v
        # init_data.update(params)
        response = Response(**init_data)
        self.manager.output_object = response
        return response

    async def push_event(
        self, event: BaseModel, output_item: Optional[ResponseOutputItem] = None
    ):
        if output_item is not None:
            self.manager.output_object.output.append(output_item)  # type: ignore
        event_label = event.__getattribute__("type")
        event_data = event.model_dump()
        self.manager.events.append(event_data)

        if self.manager.stream_to_caller:
            encoded = (
                f"event: {event_label}\ndata: {json.dumps(event_data)}\n\n"
            ).encode("utf-8")
            await self.manager.push_event(encoded)
