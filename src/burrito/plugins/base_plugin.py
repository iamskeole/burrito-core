from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Set

from pydantic import BaseModel

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

    async def put_event(self, event: BaseModel):
        await self.manager.put_event(event)
