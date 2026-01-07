from __future__ import annotations

from typing import Dict, List, Optional, Union

from openai_harmony import Author, Content, Message, Role, TextContent

from burrito.common.config import settings
from burrito.types.adapter import (
    AdapterAssistantChannel,
    AdapterConversationInputs,
    AdapterConversationInputTool,
    AdapterReasoning,
    AdapterToolNamespace,
    AdapterToolType,
)
from burrito.types.adapter.adapter_create_params_responses import (
    AdapterCreateParamsResponses,
    AdapterFunctionToolResponses,
    AdapterCustomToolResponses,
    AssistantMessage,
    AssistantReasoning,
    CustomToolCall,
    CustomToolCallOutput,
    CustomToolInputFormatText,
    CustomToolInputFormatGrammar,
    FunctionToolCall,
    FunctionToolCallOutput,
    InputItem,
    UserMessage,
    UserMessageContentImage,
    UserMessageContentText,
)


def user_message_from_text_input(user_input: str) -> Message:
    return Message(
        author=Author(role=Role.USER),
        recipient=Role.ASSISTANT.value,
        content=[TextContent(text=user_input)],
    )


# TODO: check oss implementation, individual messages PER content item? all other roles too
def user_message_from_list_input(message_data: UserMessage) -> Message:
    content = []
    for item in message_data.content:
        match item:
            case UserMessageContentText():
                content.append(TextContent(text=item.text))
            case UserMessageContentImage():
                pass  # TODO, tbd, for now gpt-oss does not support image inputs
            case _:
                pass  # maybe throw? shouldn't happen, probably too defensive
    message = Message(
        author=Author(role=Role.USER),
        content=content,
    )
    return message


def recipient_name_with_namespace(message_data: FunctionToolCall) -> Optional[str]:
    recipient_name = message_data.name
    if not recipient_name:
        return None
    # TODO; handle this properly; temporary hack to add namespace to function tools
    if "python" not in recipient_name and "browser" not in recipient_name:
        recipient_name = f"functions.{recipient_name}"
    return message_data.name


def assistant_message(
    message_data: Union[AssistantMessage, AssistantReasoning],
) -> Message:
    content: List[Content] = []
    channel: Optional[AdapterAssistantChannel] = None

    match message_data:
        case AssistantMessage():
            channel = AdapterAssistantChannel.FINAL
            content = [TextContent(text=i.text) for i in message_data.content]
        case AssistantReasoning():
            channel = AdapterAssistantChannel.ANALYSIS
            content = [TextContent(text=i.text) for i in message_data.content]
        case _:  # tool calls handled in separate function; anything else?
            pass

    message = Message(author=Author(role=Role.ASSISTANT), content=content)

    if channel:
        message.with_channel(channel=channel.value)
    return message


def tool_call_message(message_data: Union[FunctionToolCall, CustomToolCall]) -> Message:
    channel = None
    content = None
    recipient = None

    match message_data:
        case FunctionToolCall():
            channel = AdapterAssistantChannel.COMMENTARY
            content = [TextContent(text=message_data.arguments)]
            recipient = message_data.name
        case CustomToolCall():
            # TODO: maybe handle custom namespaces?
            channel = AdapterAssistantChannel.COMMENTARY
            content = [TextContent(text=message_data.input)]
            message_data.name
        case _:
            # TODO: native tool calls are probably in the analysis channel?
            pass

    # TODO: figure out linting errors, probably when handling native tools
    message = Message(author=Author(role=Role.ASSISTANT), content=content)
    message.with_channel(channel.value)
    message.with_recipient(recipient)
    return message


# TODO: figure out how to get name of tool
# TODO: handle custom tool calls and native tool calls
def tool_call_output_message(
    message_data: FunctionToolCallOutput,
    function_calls: Dict[str, Union[FunctionToolCall, CustomToolCall]],
) -> Message:
    call_id = message_data.call_id
    function_call = function_calls.get(call_id)

    assert function_call is not None, (
        f"function_call is None: {message_data.model_dump()}"
    )
    function_name = function_call.name
    if "python" not in function_name and "browser" not in function_name:
        function_name = f"functions.{function_name}"  # see above; dirty hack, address

    if function_name and "<|channel|>" in function_name:
        x = 1
    message = Message(
        author=Author(role=Role.TOOL, name=function_name),  # TODO
        content=[TextContent(text=message_data.output)],
    )
    message.with_channel(AdapterAssistantChannel.COMMENTARY.value)
    message.with_recipient(Role.ASSISTANT.value)
    return message


def input_params_to_messages(inputs: Union[str, List[InputItem]]) -> List[Message]:
    if isinstance(inputs, str):
        return [user_message_from_text_input(inputs)]

    messages: List[Message] = []
    tool_calls: Dict[str, Union[FunctionToolCall, CustomToolCall]] = {}
    for i in inputs:
        match i:
            case UserMessage():
                messages.append(user_message_from_list_input(i))

            case AssistantMessage() | AssistantReasoning():
                messages.append(assistant_message(i))

            # TODO: browser, python, other "native" tools
            # native can mean two things:
            # (1) browser and python, that the model has been trained with
            # (2) augment functions we init in designated sys prompt namespace
            # in either case, burrito will handle tool call _instead_ of caller
            # so we "pause" generation, call tool, feed to model, resume
            # and only once model processes native tool call, send back to caller
            # hence all will have to be in the analysis channel, NOT commentary
            # since that way caller will see tools called transparently but
            # will not expect to process their results, meaning we can separate
            # tools called natively from caller expectations
            case FunctionToolCall() | CustomToolCall():
                tool_calls[i.call_id] = i
                messages.append(tool_call_message(i))

            case FunctionToolCallOutput():
                # TODO: defend? output should follow call, but there's
                # a chance this will crash if the prev message is not a
                # tool call?
                # should be handled by keeping the running tally of calls?
                messages.append(tool_call_output_message(i, tool_calls))
            case CustomToolCallOutput():
                pass
    return messages


def map_input_tools(params: AdapterCreateParamsResponses):
    # TODO: handle tool_choice from params, eg auto, specific etc
    tools: List[AdapterConversationInputTool] = []
    for tool in params.tools or []:
        match tool:
            case AdapterFunctionToolResponses():
                tool = AdapterConversationInputTool(
                    name=tool.name,
                    parameters=tool.parameters,
                    strict=tool.strict,
                    type=tool.type,
                    description=tool.description or "",
                )
                tools.append(tool)

            case AdapterCustomToolResponses():
                if tool.format.type == "grammar":
                    fmt = CustomToolInputFormatGrammar(
                        definition=tool.format.definition,
                        syntax=tool.format.syntax,
                        type=tool.format.type
                    )
                else:
                    fmt = CustomToolInputFormatText(type=tool.format.type or "text")

                tool = AdapterConversationInputTool(
                    name=tool.name,
                    type=tool.type,
                    description=tool.description or "",
                    format=fmt,
                )

            # TODO: custom tools; browser, python from config or params
            # eg caller may pass a string as web_search or python? see docs
            case _:
                raise NotImplementedError("Only Function Tools implemented for now")
    return tools


def build_message_list_responses(
    params: AdapterCreateParamsResponses,
) -> AdapterConversationInputs:
    instructions = params.instructions or ""
    messages = input_params_to_messages(params.input)
    tools = map_input_tools(params)
    reasoning = params.reasoning or AdapterReasoning()

    converation_inputs = AdapterConversationInputs(
        instructions=instructions,
        messages=messages,
        tools=tools,
        reasoning=reasoning,
    )

    return converation_inputs
