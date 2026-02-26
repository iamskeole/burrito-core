from typing import Set

from anthropic.types.input_json_delta import InputJSONDelta
from anthropic.types.message import Message
from anthropic.types.raw_content_block_delta_event import RawContentBlockDeltaEvent
from anthropic.types.raw_content_block_start_event import RawContentBlockStartEvent
from anthropic.types.raw_content_block_stop_event import RawContentBlockStopEvent
from anthropic.types.tool_use_block import ToolUseBlock

from burrito.handlers.token_handler import ConversationToken
from burrito.plugins.messages.base_plugin import BasePluginMessages
from burrito.types.conversation_inputs import ConversationToolParam
from burrito.types.enums import ConversationStateEnum, ToolTypeEnum


class ToolInputPluginMessages(BasePluginMessages):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager

    def build_output_item(self) -> ToolUseBlock:
        entry = self.manager.tool_handler.register_tool_call()
        tool: ConversationToolParam = entry["tool"]
        match tool.type:
            case ToolTypeEnum.FUNCTION.value:
                return ToolUseBlock(
                    type="tool_use",
                    id=entry["call_id"],
                    input={},
                    name=tool.name,
                )
            case _:
                raise ValueError(
                    f"Expected {ToolTypeEnum.FUNCTION.value}, got {tool.type}"
                )

    @property
    def subscribed_states(self) -> Set[str]:
        return {ConversationStateEnum.TOOL_INPUT}

    async def handle_on_enter_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )
        content_block = self.build_output_item()

        self.manager.output_index += 1
        event = RawContentBlockStartEvent(
            type="content_block_start",
            index=self.manager.output_index,
            content_block=content_block,
        )
        self.manager.output_object.content.append(content_block)
        await self.put_event(event)

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

        delta = InputJSONDelta(type="input_json_delta", partial_json=token.text)
        event = RawContentBlockDeltaEvent(
            type="content_block_delta",
            index=self.manager.output_index,
            delta=delta,
        )
        await self.put_event(event)

    async def on_enter_state(self, state: ConversationStateEnum):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: ConversationStateEnum):
        await self.handle_on_exit_state()

    async def on_token(self, token: ConversationToken):
        await self.handle_on_token(token)
