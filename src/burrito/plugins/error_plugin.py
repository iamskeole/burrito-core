from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.token_handler import (
        AdapterCompletionToken,
    )
from burrito.plugins.base_plugin import BasePlugin


class ErrorPlugin(BasePlugin):
    @property
    def subscribed_states(self) -> Set[str]:
        return {"error"}

    async def on_enter_state(self, state: str):
        pass

    async def on_exit_state(self, state: str):
        pass

    async def on_token(self, token: AdapterCompletionToken):
        if self.manager.stream_to_caller:
            await self.manager._push_event(state, text=token.text)
