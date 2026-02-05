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
    ActionSearchSource,
)

from burrito.types.adapter import AdapterConversationState

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.common.utils import random_uuid
from burrito.types.adapter import AdapterCompletionToken


class NativeToolCallPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {AdapterConversationState.NATIVE_TOOL_CALL}

    async def send_browser_event(self):
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

        tool = tool_handler.browser_tool
        if not tool:
            return

        args = tool.process_arguments(last_message)

        _, function_name = recipient.split(".")
        if function_name not in ["search", "open", "find"]:
            return

        if function_name == "search":
            action = ActionSearch(query=args["query"], type="search")
            x = 1
        elif function_name == "open":
            action = ActionOpenPage(type="open_page", url=args["url"])
            x = 1
        elif function_name == "find":
            action = ActionFind(
                type="find",
                pattern=args["pattern"],
                url=args.get("url", "Unknown"),
            )
            x = 1
        else:
            return

        self.manager.output_index += 1
        output_item = ResponseFunctionWebSearch(
            id=f"ws_{random_uuid()}",
            action=action,
            status="searching",
            type="web_search_call",
        )
        # output_item = ResponseCodeInterpreterToolCall(
        #     id=f"ci_{random_uuid()}",
        #     container_id=f"burrito-cid-{random_uuid()}",
        #     code=f"print(2+2)# {random_uuid()}",
        #     status="in_progress",
        #     type="code_interpreter_call"
        # )
        event = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.added",
        )
        await self.put_event(event)
        self.manager.output_object.output.append(output_item)

        output_item.status = "completed"
        event_done = ResponseOutputItemDoneEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.done"
        )
        await self.put_event(event_done)
        
        pass

    async def send_python_event(self):
        tool_handler = self.manager.tool_handler
        last_message = self.manager.parser.messages[-1]
        if not last_message:
            return
        recipient = last_message.recipient or ""
        if not tool_handler._is_python(recipient):
            return
        pass

    async def handle_on_enter_state(self):
        await self.send_python_event()
        await self.send_browser_event()

    async def handle_on_token(self, token: AdapterCompletionToken):
        pass

    async def handle_on_exit_state(self):
        pass

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
