from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler
    from burrito.types.adapter import AdapterCompletionToken

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.types.adapter import AdapterConversationState


# TODO: decide, figure out how to implement
class ReasoningTextPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            AdapterConversationState.REASONING,
            AdapterConversationState.PREAMBLE,
        }

    async def handle_on_enter_state(self):
        pass

    async def handle_on_token(self, token: AdapterCompletionToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: AdapterCompletionToken):
        await self.handle_on_token(token)
