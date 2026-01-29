from typing import Set, List

from openai.types.chat.chat_completion_message import (
    ChatCompletionMessage,
    FunctionCall,
)
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceLogprobs,
)
from openai.types.completion_usage import CompletionUsage, CompletionTokensDetails

from burrito.types.adapter import AdapterConversationState
from burrito.types.adapter.adapter_chat_choice_delta import (
    AdapterChatChoice,
    AdapterChatChoiceDelta,
    AdapterChatCompletionChunk,
)

from burrito.plugins.chat.base_plugin import BasePluginChat


class ContextManagerPluginChat(BasePluginChat):
    def __init__(self, manager):
        super().__init__(manager)

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            AdapterConversationState.CREATED,
            AdapterConversationState.IN_PROGRESS,
            AdapterConversationState.COMPLETED,
            AdapterConversationState.TOOL_CALL,
        }

    async def handle_response_created_event(self):
        self.init_response_object()
        assert isinstance(self.manager.output_object, List), (
            f"Expected List, got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], AdapterChatCompletionChunk), (
            f"Expected ChatCompletionChunk, got {type(self.manager.output_object)}"
        )
        first_chunk = self.manager.output_object[0]
        await self.push_event(first_chunk)

    async def handle_response_in_progress_event(self):
        pass  # no in_progress events? maybe hack python / browser somehow?

    async def handle_response_completed_event(self, state: AdapterConversationState):
        assert isinstance(self.manager.output_object, List), (
            f"Expected List, got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected ChatCompletionChunk, got {type(self.manager.output_object)}"
        )

        last_token = self.manager.response_tokens[-1]
        finish_reason = last_token.finish_reason
        if state == AdapterConversationState.TOOL_CALL:
            finish_reason = "tool_calls"

        reasoning_tokens = self.manager.reasoning_tokens
        output_tokens = [
            i for i in self.manager.response_tokens if i not in reasoning_tokens
        ]

        n_input_tokens = len(self.manager.prompt_tokens)
        n_reasoning_tokens = len(reasoning_tokens)
        n_output_tokens = len(output_tokens)
        n_total_tokens = n_input_tokens + n_output_tokens

        choice = AdapterChatChoice(
            index=0,
            finish_reason=finish_reason,  # type: ignore
            # empty choice, we don't rebuild full message like responses
            delta={},
        )

        usage = CompletionUsage(
            prompt_tokens=n_input_tokens,
            completion_tokens=n_output_tokens,
            total_tokens=n_total_tokens,
            completion_tokens_details=CompletionTokensDetails(
                reasoning_tokens=n_reasoning_tokens
            ),
        )

        chunk = self.build_chunk_object(choice, usage)
        # self.manager.response_buffer, self.manager.parser
        await self.push_event(chunk)
        await self.send_close_marker()

    async def on_enter_state(self, state: AdapterConversationState):
        if state in [
            AdapterConversationState.COMPLETED,
            AdapterConversationState.TOOL_CALL,
        ]:
            await self.handle_response_completed_event(state)

        elif (
            state == AdapterConversationState.CREATED
            and not self.manager.created_event_fired
        ):
            await self.handle_response_created_event()

        elif (
            state == AdapterConversationState.IN_PROGRESS
            and not self.manager.created_event_fired
        ):
            await self.handle_response_in_progress_event()
