import json
from typing import TYPE_CHECKING, Optional, List

from openai.types.completion_usage import CompletionUsage
from burrito.types.adapter import AdapterConversationState

from burrito.types.adapter.adapter_chat_choice_delta import (
    AdapterChatCompletionChunk,
    AdapterChatChoice,
)

from burrito.common.utils import random_uuid, unix_timestamp, get_system_fingerprint
from burrito.plugins.base_plugin import BasePlugin

if TYPE_CHECKING:
    from burrito.handlers.state_handler import (
        AdapterStateHandler,
    )


class BasePluginChat(BasePlugin):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.log_extra = {"log_id": f"apr_{self.log_id}"}

    def build_chunk_object(
        self,
        choice: AdapterChatChoice,
        usage: Optional[CompletionUsage] | None = None,
    ):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], AdapterChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )
        first_chunk = self.manager.output_object[0]
        chunk_object = AdapterChatCompletionChunk(
            id=first_chunk.id,
            created=first_chunk.created,
            object="chat.completion.chunk",
            model=first_chunk.model,
            service_tier=first_chunk.service_tier,
            system_fingerprint=first_chunk.system_fingerprint,
            choices=[choice],
            usage=usage,
        )
        return chunk_object

    def init_response_object(self) -> AdapterChatCompletionChunk:
        init_data = {
            "id": f"chatcmpl-{random_uuid()}",
            "object": "chat.completion.chunk",
            "created": unix_timestamp(),
            "model": self.manager.manager.params.model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}],
            "service_tier": "default",
            "system_fingerprint": f"{get_system_fingerprint()}",
        }
        completion = AdapterChatCompletionChunk(**init_data)
        self.manager.output_object = [completion]
        return completion

    async def push_event(self, event: AdapterChatCompletionChunk):
        event_data = event.model_dump()
        self.manager.events.append(event_data)

        if self.manager.stream_to_caller:
            encoded = (f"data: {json.dumps(event_data)}\n\n").encode("utf-8")
            await self.manager.push_event(encoded)
