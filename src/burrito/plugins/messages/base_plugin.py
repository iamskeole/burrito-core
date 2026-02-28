from typing import TYPE_CHECKING

from anthropic.types import Message
from anthropic.types import Usage as AnthropicUsage

from burrito.common.utils import random_uuid
from burrito.plugins import BasePlugin

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


class BasePluginMessages(BasePlugin):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.log_extra = {"log_id": f"apr_{self.log_id}"}

    def init_response_object(self) -> Message:
        params = self.manager.manager.params.model_dump()
        token_counts = self.get_token_counts()
        message = Message(
            id=f"msg_{random_uuid()}",
            content=[],
            model=params["model"],
            role="assistant",
            type="message",
            usage=AnthropicUsage(input_tokens=token_counts.n_input, output_tokens=0),
        )
        self.manager.output_object = message
        return message

    def build_output_object(self) -> Message:  # type: ignore
        pass
