from typing import Set

from anthropic.types.message import Message
from anthropic.types.raw_content_block_delta_event import RawContentBlockDeltaEvent
from anthropic.types.raw_content_block_start_event import RawContentBlockStartEvent
from anthropic.types.raw_content_block_stop_event import RawContentBlockStopEvent
from anthropic.types.thinking_block import ThinkingBlock
from anthropic.types.thinking_delta import ThinkingDelta

from burrito.handlers.token_handler import ConversationToken
from burrito.plugins.messages.base_plugin import BasePluginMessages
from burrito.types.conversation_enums import ConversationState


class ReasoningTextPluginMessages(BasePluginMessages):
    def __init__(self, manager):
        super().__init__(manager)

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationState.REASONING,
            ConversationState.PREAMBLE,
        }

    async def handle_on_enter_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )
        self.manager.output_index += 1
        content_item = ThinkingBlock(type="thinking", signature="", thinking="")
        event_item = RawContentBlockStartEvent(
            type="content_block_start",
            content_block=content_item,
            index=self.manager.output_index,
        )
        self.manager.output_object.content.append(content_item)
        await self.put_event(event_item)

    async def handle_on_exit_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )
        event = RawContentBlockStopEvent(
            type="content_block_stop", index=self.manager.output_index
        )
        await self.put_event(event)

    async def handle_on_token(self, token: ConversationToken):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )
        delta = ThinkingDelta(type="thinking_delta", thinking=token.text)
        event = RawContentBlockDeltaEvent(
            type="content_block_delta",
            delta=delta,
            index=self.manager.output_index,
        )
        output_index = self.manager.output_index
        content_item = self.manager.output_object.content[output_index]
        assert isinstance(content_item, ThinkingBlock), (
            f"Expected a ThinkingBlock, but got {type(content_item)}"
        )
        content_item.thinking += token.text
        await self.put_event(event)

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: ConversationToken):
        await self.handle_on_token(token)
