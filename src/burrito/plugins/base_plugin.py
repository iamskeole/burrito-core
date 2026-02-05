# core/plugins/base.py
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler
    from burrito.handlers.token_handler import AdapterCompletionToken

from burrito.common.logger import FastAPILogger
from burrito.common.utils import populate_openai_typed_dict
from burrito.types.adapter import AdapterConversationState, AdapterTokenCounts


class BasePlugin(ABC):
    def __init__(self, manager: "AdapterStateHandler"):
        self.manager = manager
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = manager.log_id
        self.log_extra = {"log_id": f"abp_{self.log_id}"}

    @property
    @abstractmethod
    def subscribed_states(self) -> Set[str]:
        pass

    @staticmethod
    def _cast_type_dict(typed_dict_class: type, partial_data: dict):
        return populate_openai_typed_dict(typed_dict_class, partial_data)

    async def on_enter_state(self, state: AdapterConversationState):
        pass

    async def on_exit_state(self, state: AdapterConversationState):
        pass

    async def on_token(self, token: "AdapterCompletionToken"):
        pass

    async def on_error(self, payload: dict):
        """Emit an error event for SSE consumers.

        The original implementation suppressed errors for the ``chat``
        conversation type because *OpenAI’s chat endpoint historically never
        returned a streamed error*.  In our implementation the consumer is a
        generic SSE emitter that works for both chat and responses, so it is
        safe to always stream the error.  The routing logic will decide how
        to surface it to the final client.
        """

        event = f"event: error\ndata: {json.dumps(payload, indent=None)}\n\n"
        encoded = event.encode("utf-8")
        await self.manager.put_event(
            encoded
        )  # TODO: change to new model for manager.put BaseModel

    def get_token_counts(self) -> AdapterTokenCounts:
        n_input = len(self.manager.prompt_tokens)
        n_reasoning = len(self.manager.reasoning_tokens)
        n_preamble = len(self.manager.preamble_tokens)
        n_output_text = len(self.manager.output_text_tokens)
        n_completion = len(self.manager.response_tokens)
        n_total = n_input + n_completion

        n_native_tool_input = len(self.manager.native_tool_input_tokens)
        n_caller_tool_input = len(self.manager.caller_tool_input_tokens)

        return AdapterTokenCounts(
            n_input=n_input,
            n_reasoning=n_reasoning,
            n_preamble=n_preamble,
            n_native_tool_input=n_native_tool_input,
            n_caller_tool_input=n_caller_tool_input,
            n_output_text=n_output_text,
            n_completion=n_completion,
            n_total=n_total,
        )

    async def send_close_marker(self):
        await self.manager.put_close_marker()
