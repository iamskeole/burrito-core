from typing import TYPE_CHECKING, Literal

from openai.types.responses.response import Response
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
    ResponseUsage,
)

from burrito.common.utils import random_uuid, unix_timestamp
from burrito.plugins.base_plugin import BasePlugin
from burrito.types.conversation_enums import ConversationState

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


class BasePluginResponses(BasePlugin):
    def __init__(self, manager: "StateHandler"):
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
            "status": ConversationState.IN_PROGRESS.value,  # type: ignore
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

    async def resolve_output_object(
        self, status: Literal["completed", "incomplete"] = "completed"
    ):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected Response, got {type(self.manager.output_object)}"
        )
        self.manager.output_object.status = status

        token_counts = self.get_token_counts()

        self.manager.output_object.usage = ResponseUsage(
            input_tokens=token_counts.n_input,
            input_tokens_details=InputTokensDetails(
                cached_tokens=token_counts.n_cached
            ),
            output_tokens=token_counts.n_completion,
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=sum(
                    [
                        token_counts.n_reasoning,
                        token_counts.n_preamble,
                        token_counts.n_native_tool_input,
                    ]
                )
            ),
            total_tokens=token_counts.n_total,
        )
        for output_item in self.manager.output_object.output:
            if hasattr(output_item, "status"):
                setattr(output_item, "status", status)
