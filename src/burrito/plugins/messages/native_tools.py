from __future__ import annotations

from typing import TYPE_CHECKING, Set

from anthropic.types.input_json_delta import InputJSONDelta
from anthropic.types.message import Message
from anthropic.types.raw_content_block_delta_event import RawContentBlockDeltaEvent
from anthropic.types.raw_content_block_start_event import RawContentBlockStartEvent
from anthropic.types.raw_content_block_stop_event import RawContentBlockStopEvent
from anthropic.types.server_tool_use_block import ServerToolUseBlock
from anthropic.types.web_search_result_block import WebSearchResultBlock
from anthropic.types.web_search_tool_result_block import (
    WebSearchToolResultBlock,
)

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.types.conversation_enums import ConversationState
from burrito.types.conversation_token import ConversationToken

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


class NativeToolsPluginMessages(BasePluginResponses):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationState.NATIVE_TOOL_INPUT,
            ConversationState.NATIVE_TOOL_CALL,
            ConversationState.NATIVE_TOOL_DONE,
        }

    async def send_browser_event(self, state: ConversationState):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Message a Response, but got {type(output_object)}"
        )
        tool_handler = self.manager.tool_handler
        last_message = self.manager.conversation.messages[-1]
        if not last_message:
            return
        recipient = last_message.recipient or ""
        if not tool_handler._is_browser(recipient):
            return

        entry = self.manager.tool_handler.tool_calls[-1]
        tool = entry["tool"]
        try:
            args = tool.process_arguments(last_message)
        except Exception as e:
            return  # FIXME: why does this sometime break?

        call_id = entry["call_id"].replace("call_", "srvtoolu_")

        url = args.get("url")
        if not url:
            if args.get("cursor") == 0 and "id" in args and isinstance(args["id"], int):
                pages = tool.tool_state.pages
                serp = pages[""]
                url = serp.urls[str(args["id"])]

        _, function_name = recipient.split(".")
        if function_name not in ["search", "open", "find"]:
            return

        if function_name == "search":
            block = ServerToolUseBlock(
                type="server_tool_use",
                name="web_search",
                id=call_id,
                input={"query": args["query"]},
            )
        elif function_name == "open":
            block = ServerToolUseBlock(
                type="server_tool_use",
                name="web_search",
                id=call_id,
                input={"url": url},
            )
        # elif function_name == "find":
        #     block = ServerToolUseBlock(
        #         type="server_tool_use",
        #         name="web_search",
        #         id=call_id,
        #         input={"query": f"**{args['pattern']}**"},
        #     )
        else:
            return

        if state == ConversationState.NATIVE_TOOL_CALL:
            if function_name == "search":
                self.manager.output_index += 1
                self.manager.output_object.content.append(block)

                event_start = RawContentBlockStartEvent(
                    type="content_block_start",
                    index=self.manager.output_index,
                    content_block=block,
                )
                delta = InputJSONDelta(
                    type="input_json_delta",
                    partial_json=last_message.content[0].text,  # type: ignore
                )
                event_delta = RawContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=self.manager.output_index,
                    delta=delta,
                )
                event_stop = RawContentBlockStopEvent(
                    type="content_block_stop", index=self.manager.output_index
                )
                await self.put_event(event_start)
                await self.put_event(event_delta)
                await self.put_event(event_stop)
        else:
            # returning results seems to break claude code (2.1.37)
            # client seems to disconnect prematurely, and then inference loop ends
            # so probably the tool expects something we can't really figure out..
            # so we exit here; keep code that looks correct until a later cc version
            return
            if function_name == "search":
                call_result = tool_handler.tool_results[entry["call_id"]]

                self.manager.output_index += 1
                block = WebSearchToolResultBlock(
                    type="web_search_tool_result",
                    tool_use_id=call_id,
                    content=[
                        WebSearchResultBlock(
                            type="web_search_result",
                            title=call_result,
                            encrypted_content=call_result,
                            url=url or "",
                        )
                    ],
                )
                event_start = RawContentBlockStartEvent(
                    type="content_block_start",
                    index=self.manager.output_index,
                    content_block=block,
                )
                delta = InputJSONDelta(
                    type="input_json_delta",
                    partial_json=last_message.content[0].text,
                )
                event_delta = RawContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=self.manager.output_index,
                    delta=delta,
                )
                event_done = RawContentBlockStopEvent(
                    type="content_block_stop", index=self.manager.output_index
                )

                self.manager.output_object.content.append(block)
                await self.put_event(event_start)
                await self.put_event(event_delta)
                await self.put_event(event_done)

    async def send_python_event(self, state: ConversationState):
        pass  # claude doesn't have a code interpreter / corresponding events?

    async def handle_on_enter_state(self, state: ConversationState):
        if state == ConversationState.NATIVE_TOOL_INPUT:
            await self.manager.tool_handler.register_tool_call()
            return
        await self.send_python_event(state)
        await self.send_browser_event(state)

    async def handle_on_token(self, token: ConversationToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: ConversationState):
        await self.handle_on_enter_state(state)

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "ConversationToken"):
        await self.handle_on_token(token)
