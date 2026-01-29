# core/plugins/base.py
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import (
        AdapterStateHandler,
    )
    from burrito.handlers.token_handler import (
        AdapterCompletionToken,
    )
from burrito.common.logger import FastAPILogger
from burrito.common.utils import populate_openai_typed_dict
from burrito.types.adapter import AdapterConversationState


class BasePlugin(ABC):
    def __init__(self, manager: "AdapterStateHandler"):
        self.manager = manager
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = manager.log_id
        self.log_extra = {"log_id": f"abp_{self.log_id}"}

    @property
    @abstractmethod
    def subscribed_states(self) -> Set[str]:
        pass

    @staticmethod
    def _cast_type_dict(typed_dict_class: type, partial_data: dict):
        return populate_openai_typed_dict(typed_dict_class, partial_data)

    async def on_enter_state(self, state: AdapterConversationState):
        pass

    async def on_exit_state(self, state: AdapterConversationState):
        pass

    async def on_token(self, token: "AdapterCompletionToken"):
        pass

    async def on_error(self, payload: dict):
        """Emit an error event for SSE consumers.

        The original implementation suppressed errors for the ``chat``
        conversation type because *OpenAI’s chat endpoint historically never
        returned a streamed error*.  In our implementation the consumer is a
        generic SSE emitter that works for both chat and responses, so it is
        safe to always stream the error.  The routing logic will decide how
        to surface it to the final client.
        """

        event = f"event: error\ndata: {json.dumps(payload, indent=None)}\n\n"
        encoded = event.encode("utf-8")
        await self.manager.push_event(encoded)

    async def send_close_marker(self):
        event = "data: [DONE]\n\n"
        encoded = event.encode("utf-8")
        await self.manager.push_event(encoded)
