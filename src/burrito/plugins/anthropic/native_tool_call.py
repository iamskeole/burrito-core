from __future__ import annotations

from typing import TYPE_CHECKING, Set, Optional

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler


from anthropic.types.message import Message
from anthropic.types.content_block_start_event import ContentBlockStartEvent
from anthropic.types.content_block_delta_event import ContentBlockDeltaEvent
from anthropic.types.content_block_stop_event import ContentBlockStopEvent


from anthropic.types.server_tool_use_block import ServerToolUseBlock
from anthropic.types.web_search_result_block import WebSearchResultBlock
from anthropic.types.web_search_tool_result_block import WebSearchToolResultBlock
from anthropic.types.web_search_tool_result_error import WebSearchToolResultError
from anthropic.types.input_json_delta import InputJSONDelta

from burrito.types.adapter import AdapterConversationState

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.common.utils import random_uuid
from burrito.types.adapter import AdapterCompletionToken


class NativeToolCallPluginAnthropic(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            AdapterConversationState.NATIVE_TOOL_CALL,
            AdapterConversationState.NATIVE_TOOL_DONE,
        }

    async def send_browser_event(self, state: AdapterConversationState):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Message a Response, but got {type(output_object)}"
        )
        tool_handler = self.manager.tool_handler
        last_message = self.manager.parser.messages[-1]
        if not last_message:
            return
        recipient = last_message.recipient or ""
        if not tool_handler._is_browser(recipient):
            return

        if state == AdapterConversationState.NATIVE_TOOL_CALL:
            entry = self.manager.tool_handler.register_tool_call()
        else:
            entry = self.manager.tool_handler.tool_calls[-1]

        tool = entry["tool"]
        try:
            args = tool.process_arguments(last_message)
        except Exception as e:
            return  # TODO: why does this sometime break?

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

        if state == AdapterConversationState.NATIVE_TOOL_CALL:
            if function_name == "search":
                self.manager.output_index += 1
                self.manager.output_object.content.append(block)

                event_start = ContentBlockStartEvent(
                    type="content_block_start",
                    index=self.manager.output_index,
                    content_block=block,
                )
                delta = InputJSONDelta(
                    type="input_json_delta", partial_json=last_message.content[0].text
                )
                event_delta = ContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=self.manager.output_index,
                    delta=delta,
                )
                event_stop = ContentBlockStopEvent(
                    type="content_block_stop", index=self.manager.output_index
                )
                await self.put_event(event_start)
                await self.put_event(event_delta)
                await self.put_event(event_stop)
        else:
            return
            if function_name == "search":
                self.manager.output_index += 1
                block = WebSearchToolResultBlock(
                    type="web_search_tool_result",
                    tool_use_id=call_id,
                    content=[
                        WebSearchResultBlock(
                            type="web_search_result",
                            title="placeholder result title",
                            encrypted_content="enc",
                            url=url or "http://serp.placeholder",
                        )
                    ],
                )
                event_start = ContentBlockStartEvent(
                    type="content_block_start",
                    index=self.manager.output_index,
                    content_block=block,
                )
                delta = InputJSONDelta(
                    type="input_json_delta", partial_json=last_message.content[0].text
                )
                event_delta = ContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=self.manager.output_index,
                    delta=delta,
                )
                event_done = ContentBlockStopEvent(
                    type="content_block_stop", index=self.manager.output_index
                )

                self.manager.output_object.content.append(block)
                await self.put_event(event_start)
                await self.put_event(event_delta)
                await self.put_event(event_done)

        _tool_calls = self.manager.tool_handler.tool_calls
        _content = self.manager.output_object.content
        return

    async def send_python_event(self, state: AdapterConversationState):
        pass  # claude doesn't have a code interpreter / corresponding events?

    async def handle_on_enter_state(self, state: AdapterConversationState):
        await self.send_python_event(state)
        await self.send_browser_event(state)

    async def handle_on_token(self, token: AdapterCompletionToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: AdapterConversationState):
        await self.handle_on_enter_state(state)

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
