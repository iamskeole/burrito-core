from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set, Union

from burrito.types.adapter import AdapterConversationInputTool, AdapterConversationState

if TYPE_CHECKING:
    from burrito.adapter.handlers.state_handler import (
        AdapterStateHandler,
    )
from openai.types.responses.response import Response
from openai.types.responses.response_code_interpreter_call_code_delta_event import (
    ResponseCodeInterpreterCallCodeDeltaEvent,  # ruff: ignore
)
from openai.types.responses.response_code_interpreter_call_code_done_event import (
    ResponseCodeInterpreterCallCodeDoneEvent,
)
from openai.types.responses.response_code_interpreter_call_completed_event import (
    ResponseCodeInterpreterCallCompletedEvent,
)
from openai.types.responses.response_code_interpreter_call_in_progress_event import (
    ResponseCodeInterpreterCallInProgressEvent,
)
from openai.types.responses.response_code_interpreter_call_interpreting_event import (
    ResponseCodeInterpreterCallInterpretingEvent,
)

# python
from openai.types.responses.response_code_interpreter_tool_call import (
    ResponseCodeInterpreterToolCall,
)

# content part
from openai.types.responses.response_content_part_added_event import (
    ResponseContentPartAddedEvent,
)
from openai.types.responses.response_content_part_done_event import (
    ResponseContentPartDoneEvent,
)
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

# mcp - args
from openai.types.responses.response_mcp_call_arguments_delta_event import (
    ResponseMcpCallArgumentsDeltaEvent,
)
from openai.types.responses.response_mcp_call_arguments_done_event import (
    ResponseMcpCallArgumentsDoneEvent,
)

# mcp - call
from openai.types.responses.response_mcp_call_completed_event import (
    ResponseMcpCallCompletedEvent,
)
from openai.types.responses.response_mcp_call_failed_event import (
    ResponseMcpCallFailedEvent,
)
from openai.types.responses.response_mcp_call_in_progress_event import (
    ResponseMcpCallInProgressEvent,
)
from openai.types.responses.response_mcp_list_tools_completed_event import (
    ResponseMcpListToolsCompletedEvent,
)
from openai.types.responses.response_mcp_list_tools_failed_event import (
    ResponseMcpListToolsFailedEvent,
)

# mcp - list tools
from openai.types.responses.response_mcp_list_tools_in_progress_event import (
    ResponseMcpListToolsInProgressEvent,
)

# ------ EVENTS
# output item
from openai.types.responses.response_output_item_added_event import (
    ResponseOutputItemAddedEvent,
)
from openai.types.responses.response_output_item_done_event import (
    ResponseOutputItemDoneEvent,
)
from openai.types.responses.response_web_search_call_completed_event import (
    ResponseWebSearchCallCompletedEvent,
)

# web search
from openai.types.responses.response_web_search_call_in_progress_event import (
    ResponseWebSearchCallInProgressEvent,
)
from openai.types.responses.response_web_search_call_searching_event import (
    ResponseWebSearchCallSearchingEvent,
)

from burrito.plugins.base_plugin_responses import BasePluginResponses
from burrito.common.utils import random_uuid
from burrito.types.adapter import AdapterCompletionToken, AdapterToolNamespace
from burrito.types.adapter.adapter_tool_namespace import AdapterToolType

# TODO: remove when dome, temporary hack so linter doesn't remove imports
EVENTS = [
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseCustomToolCallInputDeltaEvent,
    ResponseCustomToolCallInputDoneEvent,
    ResponseWebSearchCallInProgressEvent,
    ResponseWebSearchCallSearchingEvent,
    ResponseWebSearchCallCompletedEvent,
    ResponseCodeInterpreterCallCodeDeltaEvent,
    ResponseCodeInterpreterCallCodeDoneEvent,
    ResponseCodeInterpreterCallCompletedEvent,
    ResponseCodeInterpreterCallInProgressEvent,
    ResponseCodeInterpreterCallInterpretingEvent,
    ResponseMcpCallArgumentsDeltaEvent,
    ResponseMcpCallArgumentsDoneEvent,
    ResponseMcpCallCompletedEvent,
    ResponseMcpCallInProgressEvent,
    ResponseMcpCallFailedEvent,
    ResponseMcpListToolsInProgressEvent,
    ResponseMcpListToolsCompletedEvent,
    ResponseMcpListToolsFailedEvent,
    # The Key Difference: Semantic Meaning
    # The primary difference is not in how the code processes them, but in what
    # they represent. The code itself doesn't define the structure of these
    # types (that would be in the codex_protocol crate), but we can infer their
    # purpose:
    #     FunctionCall: This likely represents a standard, well-defined function
    # call that the model can invoke. It probably has a rigid structure, such as
    # a name (string) and arguments (JSON string). This is analogous to the
    # standard function calling feature in models like OpenAI's GPT.
    #     CustomToolCall: This suggests a more flexible or user-defined tool
    # invocation. The term "custom tool" implies that the structure might be
    # less rigid or could be defined entirely by the user or a specific
    # integration. For example, it might have fields like tool_name and
    # input rather than name and arguments.
    ResponseFunctionToolCall,
    ResponseCustomToolCall,
]


# [
#     [x] 'event: response.created',
#     [x] 'event: response.in_progress',
#     [x] 'event: response.output_item.added',
#     [x] 'event: response.content_part.added',
#     [x] 'event: response.reasoning_text.delta',
#     [x] 'event: response.reasoning_text.done', # full reasoning string
#     [x] 'event: response.content_part.done', #TODO: missing content_part.done ?
#     [x] 'event: response.output_item.done', # content=[part(text=...)]
#     [x] 'event: response.output_item.added',
#     [x] 'event: response.content_part.added',
#     [x] 'event: response.output_text.delta',
#     [x] 'event: response.output_text.done',
#     [x] 'event: response.content_part.done',
#     [x] 'event: response.output_item.done',
#     [x] 'event: response.completed'
# ]

# TODO: figure out when / how to drop previous reasoning items

# from codex rust implementation
# https://github.com/openai/codex/blob/e899ae7d8a0c637d7a5d296481f3f48611acfdb0/codex-rs/core/src/client.rs#L826
# "response.content_part.done"
# | "response.function_call_arguments.delta"
# | "response.custom_tool_call_input.delta"
# | "response.custom_tool_call_input.done" // also emitted as response.output_item.done
# | "response.in_progress"
# | "response.output_text.done" => {}
# "response.output_item.added" => {
#     if let Some(item) = event.item.as_ref() {
#         // Detect web_search_call begin and forward a synthetic event upstream.
#         if let Some(ty) = item.get("type").and_then(|v| v.as_str())
#             && ty == "web_search_call"
#         {
#             let call_id = item
#                 .get("id")
#                 .and_then(|v| v.as_str())
#                 .unwrap_or("")
#                 .to_string();
#             let ev = ResponseEvent::WebSearchCallBegin { call_id };
#             if tx_event.send(Ok(ev)).await.is_err() {
#                 return;
#             }
#         }
#     }
# }


class ToolPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.content_index = 0

    @property
    def subscribed_states(self) -> Set[str]:
        return {AdapterConversationState.TOOL_INPUT}

    def extract_tool_name_from_recipient(self, recipient: str) -> str:
        if recipient == AdapterToolNamespace.NATIVE_PYTHON.value:
            return recipient
        elif recipient.startswith(AdapterToolNamespace.NATIVE_BROWSER.value + "."):
            return recipient  # TODO: maybe we'll have to split by method eg get, fetch

        # see if we have a tool with a namespace prefix
        try_split = recipient.split(".")
        # if no prefix, just return tool name
        if not try_split:
            return recipient
        return try_split[1] if len(try_split) > 1 else recipient

    def build_output_item(
        self,
        tool_name: str,
    ) -> Union[
        ResponseFunctionToolCall,
        ResponseCustomToolCall,
        ResponseCodeInterpreterToolCall,
    ]:
        inputs = self.manager.conversation_inputs
        tool: Optional[AdapterConversationInputTool] = None
        for i in inputs.tools or []:
            if i.name == tool_name:
                tool = i
                break

        assert tool is not None, f"Could not map tool for {tool_name}"

        match tool.type:
            # case AdapterToolType.PYTHON.value:
            #     fc_id, call_id = (f"fc_{random_uuid()}", f"call_{random_uuid()}")
            #     obj = ResponseCodeInterpreterToolCall(
            #         id=fc_id,
            #         code="",
            #         container_id="burrito",  # TODO: figure out?
            #         type="code_interpreter_call",
            #         status="in_progress",
            #     )
            #     return obj
            # case AdapterToolType.BROWSER.value:
            #     pass
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
        # TODO: use this to figure out whether native or custom tool
        # here as well, we buffer / wait to have full call built to determine tool type
        # no interim streams
        parser = self.manager.parser
        assert parser.current_recipient is not None, "parser.current_recipient is None"
        self.manager.output_index += 1

        tool_name = self.extract_tool_name_from_recipient(parser.current_recipient)
        output_item = self.build_output_item(tool_name)
        event = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.added",
        )
        await self.push_event(event, output_item)

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]
        assert output_item.id is not None, (
            f"output_item.id is None: {output_item.model_dump()}"
        )
        assert isinstance(
            output_item, (ResponseFunctionToolCall, ResponseCustomToolCall)
        ), f"Expected a ResponseCustomToolCall, but got {type(output_item)}"

        # TODO: figure out custom tools and native tools and mcp and fuckme..
        event = self.build_output_item_delta_event(token, output_item)
        await self.push_event(event)
        self.content_index += 1

    async def handle_on_exit_state(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]

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
        await self.push_event(event_output_item_done)

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
