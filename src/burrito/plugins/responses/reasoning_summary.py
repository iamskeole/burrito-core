from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler
    from burrito.types.conversation_token import ConversationToken

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.types.enums import ConversationStateEnum


# TODO: decide, figure out how to implement
class ReasoningSummaryPluginResponses(BasePluginResponses):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationStateEnum.REASONING,
            ConversationStateEnum.PREAMBLE,
        }

    async def handle_on_enter_state(self):
        pass

    async def handle_on_token(self, token: ConversationToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: ConversationToken):
        await self.handle_on_token(token)
