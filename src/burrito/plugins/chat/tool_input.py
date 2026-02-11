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


class ToolInputPluginChat(BasePluginChat):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

        self.content_index = 0
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

        args = "" if do_register else self.output_delta_buffer

        tool: AdapterConversationInputTool = entry["tool"]
        tool_type = tool.type

        match tool_type:
            case AdapterToolType.FUNCTION.value:
                tool_call = AdapterChoiceDeltaToolCall(
                    index=entry["index"],
                    function=AdapterChoiceDeltaToolCallFunction(arguments=args),
                )
            case AdapterToolType.CUSTOM.value:
                tool_call = AdapterChoiceDeltaToolCall(
                    index=entry["index"],
                    function=AdapterChoiceDeltaCustomCallFunction(input=args),
                )
            case _:
                raise ValueError(f"Expected `function` or `custom`, got {tool_type}.")

        if do_register:
            tool_call.id = entry["call_id"]
            tool_call.type = tool_type
            tool_call.function.name = tool.name  # type: ignore

        choice = AdapterChatCompletionChunkChoice(
            index=0,
            delta=AdapterChatCompletionChunkChoiceDelta(
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
        pass  # no exit event for chat/completions

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
