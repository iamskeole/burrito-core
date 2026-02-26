from __future__ import annotations

from typing import TYPE_CHECKING, List, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler
    from burrito.handlers.token_handler import ConversationToken

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from burrito.plugins.chat.base_plugin import BasePluginChat
from burrito.types.conversation_inputs import ConversationToolParam
from burrito.types.enums import ConversationStateEnum, ToolTypeEnum
from burrito.types.patched_chat_completion_chunk import (
    PatchedChatCompletionChunkChoice,
    PatchedChatCompletionChunkChoiceDelta,
    PatchedChoiceDeltaCustomCallFunction,
    PatchedChoiceDeltaToolCall,
    PatchedChoiceDeltaToolCallFunction,
)


class ToolInputPluginChat(BasePluginChat):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager

        self.content_index = 0
        self.current_output_text_content = ""
        self.output_delta_buffer = ""

    @property
    def subscribed_states(self) -> Set[str]:
        return {ConversationStateEnum.TOOL_INPUT}

    async def _send_tool_delta_event(self, do_register: bool = False):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        if do_register:
            entry = self.manager.tool_handler.register_tool_call()
        else:
            entry = self.manager.tool_handler.tool_calls[-1]

        args = "" if do_register else self.output_delta_buffer

        tool: ConversationToolParam = entry["tool"]
        tool_type = tool.type

        match tool_type:
            case ToolTypeEnum.FUNCTION.value:
                tool_call = PatchedChoiceDeltaToolCall(
                    index=entry["index"],
                    function=PatchedChoiceDeltaToolCallFunction(arguments=args),
                )
            case ToolTypeEnum.CUSTOM.value:
                tool_call = PatchedChoiceDeltaToolCall(
                    index=entry["index"],
                    function=PatchedChoiceDeltaCustomCallFunction(input=args),
                )
            case _:
                raise ValueError(f"Expected `function` or `custom`, got {tool_type}.")

        if do_register:
            tool_call.id = entry["call_id"]
            tool_call.type = tool_type
            tool_call.function.name = tool.name  # type: ignore

        choice = PatchedChatCompletionChunkChoice(
            index=0,
            delta=PatchedChatCompletionChunkChoiceDelta(
                # we don't send role or content,
                # as that can lead to empty assistant messages on some clients
                tool_calls=[tool_call]
            ),
        )
        chunk = self.build_chunk_object(choice)

        self.manager.output_object.append(chunk)
        await self.put_event(chunk)
        self.content_index += 1

        self.current_output_text_content += self.output_delta_buffer
        self.output_delta_buffer = ""

    async def handle_on_enter_state(self):
        await self._send_tool_delta_event(do_register=True)

    async def handle_on_token(self, token: ConversationToken):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        self.output_delta_buffer = token.text
        await self._send_tool_delta_event()

    async def handle_on_exit_state(self):
        pass  # no exit event for chat/completions

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "ConversationToken"):
        await self.handle_on_token(token)
