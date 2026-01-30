from __future__ import annotations

from typing import TYPE_CHECKING, Set, List

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler
    from burrito.types.adapter import AdapterCompletionToken

from burrito.types.adapter.adapter_chat_completion_chunk import (
    AdapterChatCompletionChunk,
    AdapterChatCompletionChunkChoice,
    AdapterChatCompletionChunkChoiceDelta,
)
from burrito.plugins.chat.base_plugin import BasePluginChat


class ReasoningTextPluginChat(BasePluginChat):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.content_index = 0

    @property
    def subscribed_states(self) -> Set[str]:
        return {"reasoning"}

    async def handle_on_enter_state(self):
        pass  # no enter event for chat/completions

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], AdapterChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        choice = AdapterChatCompletionChunkChoice(
            index=0,
            delta=AdapterChatCompletionChunkChoiceDelta(
                role="assistant",  # TODO, maybe tool?
                reasoning_content=token.text,
            ),
        )
        chunk = self.build_chunk_object(choice)

        self.manager.output_object.append(chunk)
        await self.push_event(chunk)
        self.content_index += 1

    async def handle_on_exit_state(self):
        pass  # no exit event for chat/completions

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: AdapterCompletionToken):
        await self.handle_on_token(token)
