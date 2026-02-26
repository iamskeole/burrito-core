from typing import List, Set

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from burrito.plugins.chat.base_plugin import BasePluginChat
from burrito.types.enums import ConversationStateEnum
from burrito.types.patched_chat_completion_chunk import (
    PatchedChatCompletionChunk,
    PatchedChatCompletionChunkChoice,
)


class ContextManagerPluginChat(BasePluginChat):
    def __init__(self, manager):
        super().__init__(manager)

        self.sent_created_event = False
        self.sent_in_progress_event = False

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationStateEnum.CREATED,
            ConversationStateEnum.IN_PROGRESS,
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.TOOL_CALL,
        }

    async def handle_response_created_event(self):
        if self.sent_created_event:
            return
        self.init_response_object()
        assert isinstance(self.manager.output_object, List), (
            f"Expected List, got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], PatchedChatCompletionChunk), (
            f"Expected ChatCompletionChunk, got {type(self.manager.output_object)}"
        )
        first_chunk = self.manager.output_object[0]
        await self.put_event(first_chunk)
        self.sent_created_event = True

    async def handle_response_in_progress_event(self):
        if self.sent_in_progress_event:
            return
        pass  # no in_progress events? maybe hack python / browser somehow?

    async def handle_response_completed_event(self, state: ConversationStateEnum):
        assert isinstance(self.manager.output_object, List), (
            f"Expected List, got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected ChatCompletionChunk, got {type(self.manager.output_object)}"
        )

        last_token = self.manager.response_tokens[-1]
        finish_reason = last_token.finish_reason
        if state == ConversationStateEnum.TOOL_CALL:
            finish_reason = "tool_calls"

        choice = PatchedChatCompletionChunkChoice(
            index=0,
            finish_reason=finish_reason,  # type: ignore
            # empty choice, we don't rebuild full message like responses
            delta={},
        )
        chunk = self.build_chunk_object(choice)
        self.manager.output_object.append(chunk)
        await self.put_event(chunk)
        await self.send_close_marker()
        self.build_output_object()

    async def on_enter_state(self, state: ConversationStateEnum):
        if state == ConversationStateEnum.CREATED:
            await self.handle_response_created_event()

        if state == ConversationStateEnum.IN_PROGRESS:
            await self.handle_response_in_progress_event()

        if state in [
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.TOOL_CALL,
        ]:
            await self.handle_response_completed_event(state)
