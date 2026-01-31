from __future__ import annotations

from typing import TYPE_CHECKING, Set, List

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler
    from burrito.handlers.token_handler import AdapterCompletionToken

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from burrito.types.adapter.adapter_chat_completion_chunk import (
    AdapterChatCompletionChunkChoice,
    AdapterChatCompletionChunkChoiceDelta,
    AdapterChoiceDeltaToolCall,
    AdapterChoiceDeltaToolCallFunction,
    AdapterChoiceDeltaCustomCallFunction,
)

from burrito.types.adapter import AdapterConversationInputTool, AdapterConversationState
from burrito.types.adapter.adapter_tool_namespace import AdapterToolType

from burrito.plugins.chat.base_plugin import BasePluginChat


class ToolPluginChat(BasePluginChat):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

        self.content_index = 0
        self.current_annotations = []
        self.current_output_text_content = ""
        self.output_delta_buffer = ""

    @property
    def subscribed_states(self) -> Set[str]:
        return {AdapterConversationState.TOOL_INPUT}

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

        args_or_input = "" if do_register else self.output_delta_buffer

        tool: AdapterConversationInputTool = entry["tool"]
        tool_type = tool.type

        assert tool_type in [
            AdapterToolType.FUNCTION.value,
            AdapterToolType.CUSTOM.value,
        ], f"Expected `function` or `custom`, got {tool_type}."

        match tool_type:
            case AdapterToolType.FUNCTION.value:
                tool_call = AdapterChoiceDeltaToolCall(
                    index=entry["index"],
                    id=entry["call_id"],
                    function=AdapterChoiceDeltaToolCallFunction(
                        name=tool.name, arguments=args_or_input
                    ),
                    type=tool_type,
                )
            case AdapterToolType.CUSTOM.value:
                tool_call = AdapterChoiceDeltaToolCall(
                    index=entry["index"],
                    id=entry["call_id"],
                    function=AdapterChoiceDeltaCustomCallFunction(
                        name=tool.name, input=args_or_input
                    ),
                    type=tool_type,
                )
            case _:
                raise ValueError(f"Expected `function` or `custom`, got {tool_type}.")

        choice = AdapterChatCompletionChunkChoice(
            index=0,
            delta=AdapterChatCompletionChunkChoiceDelta(
                role="assistant", content="", tool_calls=[tool_call]
            ),
        )
        chunk = self.build_chunk_object(choice)

        self.manager.output_object.append(chunk)
        await self.push_event(chunk)
        self.content_index += 1

        self.current_output_text_content += self.output_delta_buffer
        self.output_delta_buffer = ""

    async def handle_on_enter_state(self):
        await self._send_tool_delta_event(do_register=True)

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        self.output_delta_buffer = token.text
        await self._send_tool_delta_event()

    async def handle_on_exit_state(self):
        pass  # no exit event for chat/completions BUT? maybe need to call done if tool call flag?

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
