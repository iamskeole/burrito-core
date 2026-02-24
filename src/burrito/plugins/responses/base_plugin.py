from typing import TYPE_CHECKING

from openai.types.responses.response import Response

from burrito.common.utils import random_uuid, unix_timestamp
from burrito.plugins.base_plugin import BasePlugin
from burrito.types.adapter import AdapterConversationState

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler


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
