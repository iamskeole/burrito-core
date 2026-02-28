from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Set

from pydantic import BaseModel

from burrito.common.logger import FastAPILogger
from burrito.types.conversation_enums import ConversationState
from burrito.types.conversation_usage import ConversationUsage

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler
    from burrito.handlers.token_handler import ConversationToken


class BasePlugin(ABC):
    def __init__(self, manager: "StateHandler"):
        self.manager = manager
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = manager.log_id
        self.log_extra = {"log_id": f"abp_{self.log_id}"}

    @property
    @abstractmethod
    def subscribed_states(self) -> Set[str]:
        pass

    async def on_enter_state(self, state: ConversationState):
        pass

    async def on_exit_state(self, state: ConversationState):
        pass

    async def on_token(self, token: "ConversationToken"):
        pass

    def get_token_counts(self) -> ConversationUsage:
        n_input = len(self.manager.prompt_tokens)
        n_reasoning = len(self.manager.reasoning_tokens)
        n_preamble = len(self.manager.preamble_tokens)
        n_output_text = len(self.manager.output_text_tokens)
        n_completion = len(self.manager.response_tokens)
        n_total = n_input + n_completion

        n_native_tool_input = len(self.manager.native_tool_input_tokens)
        n_caller_tool_input = len(self.manager.caller_tool_input_tokens)

        # best effort estimate, doesn't seem we can get actual counts from backend
        # may disable eventually, adds sme overhead on each token, not
        # sure whether actually brings any value?
        n_cached = 0
        if n_completion:
            tft = self.manager.response_tokens[0].created_at
            tlt = self.manager.response_tokens[-1].created_at
            ttft = (tft - self.manager.created_at) / 1000
            t_completion = (tlt - tft) / 1000 + 1e-9
            tps_prompt = n_input / ttft
            tps_eval = n_completion / t_completion
            if tps_prompt / tps_eval > 20:
                n_cached = n_input

        return ConversationUsage(
            n_input=n_input,
            n_reasoning=n_reasoning,
            n_preamble=n_preamble,
            n_native_tool_input=n_native_tool_input,
            n_caller_tool_input=n_caller_tool_input,
            n_output_text=n_output_text,
            n_completion=n_completion,
            n_total=n_total,
            n_cached=n_cached,
        )

    async def send_close_marker(self):
        await self.manager.put_close_marker()

    async def put_event(self, event: BaseModel):
        await self.manager.put_event(event)
