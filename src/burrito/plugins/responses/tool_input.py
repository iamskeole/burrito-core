from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set, Union

from burrito.types.adapter import AdapterConversationInputTool, AdapterConversationState

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler

from openai.types.responses.response import Response

from openai.types.responses.response_custom_tool_call import ResponseCustomToolCall

# custom tools
from openai.types.responses.response_custom_tool_call_input_delta_event import (
    ResponseCustomToolCallInputDeltaEvent,
)
from openai.types.responses.response_custom_tool_call_input_done_event import (
    ResponseCustomToolCallInputDoneEvent,
)

# function calls
from openai.types.responses.response_function_call_arguments_delta_event import (
    ResponseFunctionCallArgumentsDeltaEvent,
)
from openai.types.responses.response_function_call_arguments_done_event import (
    ResponseFunctionCallArgumentsDoneEvent,
)
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall

from openai.types.responses.response_output_item_added_event import (
    ResponseOutputItemAddedEvent,
)
from openai.types.responses.response_output_item_done_event import (
    ResponseOutputItemDoneEvent,
)

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.common.utils import random_uuid
from burrito.types.adapter import AdapterCompletionToken
from burrito.types.adapter.adapter_tool_namespace import AdapterToolType


class ToolInputPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

    @property
    def subscribed_states(self) -> Set[str]:
        return {AdapterConversationState.TOOL_INPUT}

    def build_output_item(
        self,
        tool_name: str,
    ) -> Optional[
        Union[
            ResponseFunctionToolCall,
            ResponseCustomToolCall,
        ]
    ]:
        inputs = self.manager.conversation_inputs
        tool: Optional[AdapterConversationInputTool] = None
        for i in inputs.tools or []:
            if i.name == "browser" and tool_name.startswith("browser."):
                tool = i
                break

            if i.name == tool_name:
                tool = i
                break

        assert tool is not None, f"Could not map tool for {tool_name}"
        # TODO: match the chat implementation, way more robust
        # need to register tool call in tool_handler
        match tool.type:
            case AdapterToolType.PYTHON.value:
                return  # always handle "internally" in model CoT
            case AdapterToolType.BROWSER.value:
                return  # always handle "internally" in model CoT
            case AdapterToolType.FUNCTION.value:
                fc_id, call_id = (f"fc_{random_uuid()}", f"call_{random_uuid()}")
                return ResponseFunctionToolCall(
                    call_id=call_id,
                    name=tool_name,
                    type="function_call",
                    id=fc_id,
                    status="in_progress",
                    arguments="",
                )
            case AdapterToolType.CUSTOM.value:
                fc_id, call_id = (f"ctc_{random_uuid()}", f"call_{random_uuid()}")
                return ResponseCustomToolCall(
                    call_id=call_id,
                    input="",
                    name=tool_name,
                    type="custom_tool_call",
                    id=fc_id,
                )
            case _:
                raise ValueError(f"Unknown tool type: {tool.type}")

    def build_output_item_delta_event(
        self,
        token: AdapterCompletionToken,
        output_item: Union[ResponseFunctionToolCall, ResponseCustomToolCall],
    ) -> Union[
        ResponseFunctionCallArgumentsDeltaEvent, ResponseCustomToolCallInputDeltaEvent
    ]:
        self.manager.response_buffer
        assert output_item.id is not None, "output_item.id is None"
        if isinstance(output_item, ResponseFunctionToolCall):
            # TODO: this looks sane, but double check if we're supposed to add to buffer
            output_item.arguments += token.text
            return ResponseFunctionCallArgumentsDeltaEvent(
                delta=token.text,
                item_id=output_item.id,
                output_index=self.manager.output_index,
                sequence_number=self.manager.sequence_number,
                type="response.function_call_arguments.delta",
            )
        else:
            output_item.input += token.text
            return ResponseCustomToolCallInputDeltaEvent(
                delta=token.text,
                item_id=output_item.id,
                output_index=self.manager.output_index,
                sequence_number=self.manager.sequence_number,
                type="response.custom_tool_call_input.delta",
            )

    def build_output_item_done_event(
        self, output_item: Union[ResponseFunctionToolCall, ResponseCustomToolCall]
    ) -> Union[
        ResponseFunctionCallArgumentsDoneEvent,
        ResponseCustomToolCallInputDoneEvent,
        None,
    ]:
        assert output_item.id is not None, "output_item.id is None"
        match output_item:
            case ResponseFunctionToolCall():
                return ResponseFunctionCallArgumentsDoneEvent(
                    arguments=output_item.arguments,
                    name=output_item.name,
                    item_id=output_item.id,
                    output_index=self.manager.output_index,
                    sequence_number=self.manager.sequence_number,
                    type="response.function_call_arguments.done",
                )
            case ResponseCustomToolCallInputDoneEvent():
                return ResponseCustomToolCallInputDoneEvent(
                    input=output_item.input,
                    item_id=output_item.id,
                    output_index=self.manager.output_index,
                    sequence_number=self.manager.sequence_number,
                    type="response.custom_tool_call_input.done",
                )
            case _:
                return

    async def handle_on_enter_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(output_object)}"
        )
        self.manager.output_index += 1
        entry = self.manager.tool_handler.register_tool_call()
        tool: AdapterConversationInputTool = entry["tool"]
        output_item = self.build_output_item(tool.name)
        if not output_item:
            return

        event = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.added",
        )
        self.manager.output_object.output.append(output_item)
        await self.put_event(event)

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        try:
            output_item = self.manager.output_object.output[self.manager.output_index]
        except IndexError:
            raise  # TODO: investigate, why out of range?
        if not output_item:
            return

        assert output_item.id is not None, (
            f"output_item.id is None: {output_item.model_dump()}"
        )
        assert isinstance(
            output_item,
            (
                ResponseFunctionToolCall,
                ResponseCustomToolCall,
            ),
        ), f"Expected a ResponseCustomToolCall, but got {type(output_item)}"

        # TODO: figure out custom tools and native tools and mcp and fuckme..
        event = self.build_output_item_delta_event(token, output_item)
        await self.put_event(event)

    async def handle_on_exit_state(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]
        if not output_item:
            return

        assert isinstance(
            output_item, (ResponseFunctionToolCall, ResponseCustomToolCall)
        ), (
            f"Expected a ResponseFunctionToolCall or ResponseCustomToolCall, but got {type(output_item)}"
        )
        assert output_item.call_id is not None, (
            f"output_item.call_id is None: {output_item.model_dump()}"
        )

        event_output_item_done = self.build_output_item_done_event(output_item)
        assert event_output_item_done is not None, "event_output_item_done is None"
        event_output_item_done = ResponseOutputItemDoneEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.done",
        )
        await self.put_event(event_output_item_done)

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
