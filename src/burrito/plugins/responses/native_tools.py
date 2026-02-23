from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler

from openai.types.responses.response import Response

from openai.types.responses.response_output_item_added_event import (
    ResponseOutputItemAddedEvent,
)
from openai.types.responses.response_output_item_done_event import (
    ResponseOutputItemDoneEvent,
)

from openai.types.responses.response_code_interpreter_tool_call import (
    ResponseCodeInterpreterToolCall,
)

from openai.types.responses.response_function_web_search import (
    ResponseFunctionWebSearch,
    ActionFind,
    ActionOpenPage,
    ActionSearch,
)

from burrito.types.adapter import AdapterConversationState

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.common.utils import random_uuid
from burrito.types.adapter import AdapterCompletionToken


class NativeToolsPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            AdapterConversationState.NATIVE_TOOL_INPUT,
            AdapterConversationState.NATIVE_TOOL_CALL,
            AdapterConversationState.NATIVE_TOOL_DONE,
        }

    async def send_browser_event(self, state: AdapterConversationState):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(output_object)}"
        )
        tool_handler = self.manager.tool_handler
        last_message = self.manager.parser.messages[-1]
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
            return  # TODO: why does this sometime break?

        _, function_name = recipient.split(".")
        if function_name not in ["search", "open", "find"]:
            return

        if function_name == "search":
            action = ActionSearch(query=args["query"], type="search")
        elif function_name == "open":
            action = ActionOpenPage(type="open_page", url=args["url"])
        elif function_name == "find":
            action = ActionFind(
                type="find",
                pattern=f"**{args['pattern']}**",
                url=args.get("url", "Unknown"),
            )
        else:
            return

        if state == AdapterConversationState.NATIVE_TOOL_CALL:
            self.manager.output_index += 1
            output_item = ResponseFunctionWebSearch(
                id=f"ws_{random_uuid()}",
                action=action,
                status="searching",
                type="web_search_call",
            )
            event = ResponseOutputItemAddedEvent(
                item=output_item,
                output_index=self.manager.output_index,
                sequence_number=self.manager.sequence_number,
                type="response.output_item.added",
            )
            self.manager.output_object.output.append(output_item)
        else:
            output_item = self.manager.output_object.output[self.manager.output_index]
            assert isinstance(output_item, ResponseFunctionWebSearch), (
                f"Expected ResponseFunctionWebSearch, got '{type(output_item)}'."
            )
            output_item.status = "completed"
            event = ResponseOutputItemDoneEvent(
                item=output_item,
                output_index=self.manager.output_index,
                sequence_number=self.manager.sequence_number,
                type="response.output_item.done",
            )
        await self.put_event(event)

    async def send_python_event(self, state: AdapterConversationState):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(output_object)}"
        )
        tool_handler = self.manager.tool_handler
        last_message = self.manager.parser.messages[-1]
        if not last_message:
            return
        recipient = last_message.recipient or ""
        if not tool_handler._is_python(recipient):
            return

        if state == AdapterConversationState.NATIVE_TOOL_CALL:
            self.manager.output_index += 1
            output_item = ResponseCodeInterpreterToolCall(
                id=f"ci_{random_uuid()}",
                container_id=f"burrito-cid-{random_uuid()}",
                code=last_message.content[0].text,  # type: ignore
                status="in_progress",
                type="code_interpreter_call",
            )
            event = ResponseOutputItemAddedEvent(
                item=output_item,
                output_index=self.manager.output_index,
                sequence_number=self.manager.sequence_number,
                type="response.output_item.added",
            )
            self.manager.output_object.output.append(output_item)
        else:
            output_item = self.manager.output_object.output[self.manager.output_index]
            assert isinstance(output_item, ResponseCodeInterpreterToolCall), (
                f"Expected ResponseCodeInterpreterToolCall, got '{type(output_item)}'."
            )
            output_item.status = "completed"
            event = ResponseOutputItemDoneEvent(
                item=output_item,
                output_index=self.manager.output_index,
                sequence_number=self.manager.sequence_number,
                type="response.output_item.done",
            )
        await self.put_event(event)

    async def handle_on_enter_state(self, state: AdapterConversationState):
        if state == AdapterConversationState.NATIVE_TOOL_INPUT:
            self.manager.tool_handler.register_tool_call()
            return
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
