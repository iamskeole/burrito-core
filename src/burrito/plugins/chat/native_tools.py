from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


from burrito.plugins.chat.base_plugin import BasePluginChat
from burrito.types.conversation_token import ConversationToken
from burrito.types.enums import ConversationStateEnum


class NativeToolsPluginChat(BasePluginChat):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationStateEnum.NATIVE_TOOL_INPUT,
        }

    async def send_browser_event(self, state: ConversationStateEnum):
        pass  # no events for chat/completions

    async def send_python_event(self, state: ConversationStateEnum):
        pass  # no events for chat/completions

    async def handle_on_enter_state(self, state: ConversationStateEnum):
        if state == ConversationStateEnum.NATIVE_TOOL_INPUT:
            self.manager.tool_handler.register_tool_call()
            return

    async def handle_on_token(self, token: ConversationToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: ConversationStateEnum):
        await self.handle_on_enter_state(state)

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "ConversationToken"):
        await self.handle_on_token(token)
