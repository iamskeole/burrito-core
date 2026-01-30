from __future__ import annotations

from typing import Dict, List, Optional, Union

from openai_harmony import Author, Content, Message, Role, TextContent

from burrito.types.adapter import (
    AdapterAssistantChannel,
    AdapterConversationInputs,
    AdapterConversationInputTool,
    AdapterReasoningParam,
)
from burrito.types.adapter.adapter_create_params_responses import (
    AdapterCreateParamsResponses,
    AssistantMessageParamResponses,
    AssistantReasoningParamResponses,
    CustomToolInputParamResponses,
    CustomToolCallOutputParamResponses,
    FunctionToolInputParamResponses,
    ToolCallOutputParamResponses,
    InputItemParamResponses,
    UserMessageParamResponses,
    UserMessageContentImageParamResponses,
    UserMessageContentTextParamResponses,
)

from burrito.types.adapter.adapter_function_tool_param import (
    AdapterFunctionToolParamResponses,
)
from burrito.types.adapter.adapter_custom_tool_param import (
    AdapterCustomToolParamResponses,
    CustomToolInputFormatText,
    CustomToolInputFormatGrammar,
)

from burrito.types.adapter.adapter_web_search_tool_param import (
    AdapterWebSearchToolParamResponses,
)


def user_message_from_text_input(user_input: str) -> Message:
    return Message(
        author=Author(role=Role.USER),
        recipient=Role.ASSISTANT.value,
        content=[TextContent(text=user_input)],
    )


# TODO: check oss implementation, individual messages PER content item? all other roles too
def user_message_from_list_input(message_data: UserMessageParamResponses) -> Message:
    content = []
    for item in message_data.content:
        match item:
            case UserMessageContentTextParamResponses():
                content.append(TextContent(text=item.text))
            case UserMessageContentImageParamResponses():
                pass  # TODO, tbd, for now gpt-oss does not support image inputs
            case _:
                pass  # maybe throw? shouldn't happen, probably too defensive
    message = Message(
        author=Author(role=Role.USER),
        content=content,
    )
    return message


def assistant_message(
    message_data: Union[
        AssistantMessageParamResponses, AssistantReasoningParamResponses
    ],
) -> Message:
    content: List[Content] = []
    channel: Optional[AdapterAssistantChannel] = None

    match message_data:
        case AssistantMessageParamResponses():
            channel = AdapterAssistantChannel.FINAL
            content = [TextContent(text=i.text) for i in message_data.content]
        case AssistantReasoningParamResponses():
            channel = AdapterAssistantChannel.ANALYSIS
            content = [TextContent(text=i.text) for i in message_data.content]
        case _:  # tool calls handled in separate function; anything else?
            pass

    message = Message(author=Author(role=Role.ASSISTANT), content=content)

    if channel:
        message.with_channel(channel=channel.value)
    return message


def tool_call_input_message(
    message_data: Union[FunctionToolInputParamResponses, CustomToolInputParamResponses],
) -> Message:
    content: List[Content]
    recipient: str

    match message_data:
        case FunctionToolInputParamResponses():
            content = [TextContent(text=message_data.arguments)]
            recipient = message_data.name
        case CustomToolInputParamResponses():
            # TODO: maybe handle custom namespaces?
            content = [TextContent(text=message_data.input)]
            recipient = message_data.name
        case _:
            raise (
                NotImplementedError,
                f"Unsupported message data type: {type(message_data)}",
            )

    message = Message(author=Author(role=Role.ASSISTANT), content=content)
    message.with_channel(AdapterAssistantChannel.COMMENTARY.value)
    message.with_recipient(recipient)
    return message


# TODO: handle custom tool calls and native tool calls
def tool_call_output_message(
    message_data: ToolCallOutputParamResponses,
    function_calls: Dict[
        str,
        Union[FunctionToolInputParamResponses, CustomToolInputParamResponses],
    ],
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


def input_params_to_messages(
    inputs: Union[str, List[InputItemParamResponses]],
) -> List[Message]:
    if isinstance(inputs, str):
        return [user_message_from_text_input(inputs)]

    messages: List[Message] = []
    tool_calls: Dict[
        str,
        Union[FunctionToolInputParamResponses, CustomToolInputParamResponses],
    ] = {}
    for i in inputs:
        match i:
            case FunctionToolInputParamResponses() | CustomToolInputParamResponses():
                tool_calls[i.call_id] = i

    for i in inputs:
        match i:
            case UserMessageParamResponses():
                messages.append(user_message_from_list_input(i))

            case AssistantMessageParamResponses() | AssistantReasoningParamResponses():
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
            case FunctionToolInputParamResponses() | CustomToolInputParamResponses():
                # tool_calls[i.call_id] = i
                messages.append(tool_call_input_message(i))

            case ToolCallOutputParamResponses():
                # TODO: defend? output should follow call, but there's
                # a chance this will crash if the prev message is not a
                # tool call?
                # should be handled by keeping the running tally of calls?
                messages.append(tool_call_output_message(i, tool_calls))
            case CustomToolCallOutputParamResponses():
                pass
    return messages


def map_input_tools(
    params: AdapterCreateParamsResponses,
) -> List[AdapterConversationInputTool]:
    # TODO: handle tool_choice from params, eg auto, specific etc
    tools: List[AdapterConversationInputTool] = []
    for tool in params.tools or []:
        match tool:
            case AdapterFunctionToolParamResponses():
                tool = AdapterConversationInputTool(
                    name=tool.name,
                    parameters=tool.parameters,
                    strict=tool.strict,
                    type=tool.type,
                    description=tool.description or "",
                )
                tools.append(tool)

            case AdapterCustomToolParamResponses():
                fmt = None
                if tool.format:
                    if tool.format.type == "grammar":
                        fmt = CustomToolInputFormatGrammar(
                            definition=tool.format.definition,
                            syntax=tool.format.syntax,
                            type=tool.format.type,
                        )
                    else:
                        fmt = CustomToolInputFormatText(type=tool.format.type or "text")

                tool = AdapterConversationInputTool(
                    name=tool.name,
                    type=tool.type,
                    description=tool.description or "",
                    format=fmt,
                )

            case AdapterWebSearchToolParamResponses():
                continue  # we handle web search natively

            case _:
                raise NotImplementedError(f"Unsupported tool type: {type(tool)}")
    return tools


def build_message_list_responses(
    params: AdapterCreateParamsResponses,
) -> AdapterConversationInputs:
    instructions = params.instructions or ""
    messages = input_params_to_messages(params.input)
    tools = map_input_tools(params)
    reasoning = params.reasoning or AdapterReasoningParam()

    converation_inputs = AdapterConversationInputs(
        instructions=instructions,
        messages=messages,
        tools=tools,
        reasoning=reasoning,
    )

    return converation_inputs
