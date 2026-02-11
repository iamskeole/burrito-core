from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from openai.types.completion_usage import CompletionUsage
from anthropic.types.text_block import TextBlock
from anthropic.types.thinking_block import ThinkingBlock
from anthropic.types.tool_use_block import ToolUseBlock
from anthropic.types import (
    RawMessageStartEvent,
    RawMessageStopEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    Message,
    Usage as AnthropicUsage,
    TextDelta,
    ThinkingDelta,
    InputJSONDelta,
)
from anthropic.types.raw_content_block_delta_event import (
    RawContentBlockDeltaEvent,
)
from anthropic.types.raw_message_delta_event import (
    Delta as MessageDelta,
    RawMessageDeltaEvent,
)

from anthropic.types.message_delta_usage import MessageDeltaUsage

from burrito.plugins import BasePlugin
from burrito.types.adapter import AdapterConversationState

from burrito.common.utils import random_uuid, unix_timestamp

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler


class BasePluginAnthropic(BasePlugin):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.log_extra = {"log_id": f"apr_{self.log_id}"}

    def init_response_object(self) -> Message:
        params = self.manager.manager.params.model_dump()
        message = Message(
            id=f"msg_{random_uuid()}",
            content=[],
            model=params["model"],
            role="assistant",
            type="message",
            usage=AnthropicUsage(
                input_tokens=self.get_token_counts().n_input, output_tokens=0
            ),
        )
        self.manager.output_object = message
        return message

    def build_output_object(self) -> Message:
        pass
