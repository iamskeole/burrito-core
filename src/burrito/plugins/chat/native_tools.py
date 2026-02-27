from __future__ import annotations

from typing import TYPE_CHECKING, Set

from burrito.plugins.chat.base_plugin import BasePluginChat
from burrito.types.conversation_enums import ConversationState
from burrito.types.conversation_token import ConversationToken

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


class NativeToolsPluginChat(BasePluginChat):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationState.NATIVE_TOOL_INPUT,
        }

    async def send_browser_event(self, state: ConversationState):
        pass  # no events for chat/completions

    async def send_python_event(self, state: ConversationState):
        pass  # no events for chat/completions

    async def handle_on_enter_state(self, state: ConversationState):
        if state == ConversationState.NATIVE_TOOL_INPUT:
            self.manager.tool_handler.register_tool_call()
            return

    async def handle_on_token(self, token: ConversationToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: ConversationState):
        await self.handle_on_enter_state(state)

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "ConversationToken"):
        await self.handle_on_token(token)
