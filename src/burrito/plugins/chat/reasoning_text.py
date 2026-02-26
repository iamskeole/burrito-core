from __future__ import annotations

from typing import TYPE_CHECKING, List, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler
    from burrito.types.conversation_token import ConversationToken

from burrito.plugins.chat.base_plugin import BasePluginChat
from burrito.types.enums import ConversationStateEnum
from burrito.types.patched_chat_completion_chunk import (
    PatchedChatCompletionChunk,
    PatchedChatCompletionChunkChoice,
    PatchedChatCompletionChunkChoiceDelta,
)


class ReasoningTextPluginChat(BasePluginChat):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            # NOTE: if we comment out .REASONING, only shows preamble to users
            # this is the official guideline for gpt-oss, but since we're
            # running locally, responsibility should be client's, we expose
            # everything here so caller can decide ui stuff
            ConversationStateEnum.REASONING,
            ConversationStateEnum.PREAMBLE,
        }

    async def handle_on_enter_state(self):
        pass  # no enter event for chat/completions

    async def handle_on_token(self, token: ConversationToken):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], PatchedChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        choice = PatchedChatCompletionChunkChoice(
            index=0,
            delta=PatchedChatCompletionChunkChoiceDelta(
                role="assistant",
                reasoning_content=token.text,
            ),
        )
        chunk = self.build_chunk_object(choice)
        self.manager.output_object.append(chunk)
        await self.put_event(chunk)

    async def handle_on_exit_state(self):
        pass  # no exit event for chat/completions

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: ConversationToken):
        await self.handle_on_token(token)
