from __future__ import annotations

from typing import List, Dict

from openai_harmony import Message, Author, Role, Content, TextContent

from burrito.types.adapter import (
    AdapterAssistantChannel,
    AdapterConversationInputs,
    AdapterCreateParamsChat,
    AdapterConversationInputTool,
    AdapterReasoningParam,
)

from burrito.types.adapter.adapter_create_params_chat import (
    UserMessageParamChat,
    ContentPartText,
    ContentPartImageUrl,
    AssistantMessageParamChat,
    ToolCallOutputParamChat,
    DeveloperMessageParamChat,
    SystemMessageParamChat,
    AssistantToolCallParamChat,
)

from burrito.types.adapter.adapter_function_tool_param import (
    AdapterFunctionToolParamChat,
)
from burrito.types.adapter.adapter_custom_tool_param import (
    AdapterCustomToolParamChat,
    CustomToolInputFormatText,
    CustomToolInputFormatGrammar,
)


def user_message(message_data: UserMessageParamChat) -> Message:
    content: List[Content] = []
    if isinstance(message_data.content, str):
        content.append(TextContent(text=message_data.content))
    elif isinstance(message_data.content, list):
        for item in message_data.content:
            match item:
                case ContentPartText():
                    content.append(TextContent(text=item.text))
                case ContentPartImageUrl():
                    pass  # TODO: tbd, only text supported by gpt-oss
                case _:
                    pass  # throw?
    else:
        pass  # throw?

    message = Message(author=Author(role=Role.USER), content=content)
    return message


def assistant_message(
    message_data: AssistantMessageParamChat,
    tool_calls: Dict[str, AssistantToolCallParamChat],
) -> Message:
    content: List[Content] = []
    channel = None

    if message_data.content is None or message_data.tool_calls is not None:
        channel = AdapterAssistantChannel.COMMENTARY
    else:
        channel = AdapterAssistantChannel.FINAL

    if message_data.tool_calls is None:
        channel = AdapterAssistantChannel.FINAL
    else:
        channel = AdapterAssistantChannel.COMMENTARY

    content.append(TextContent(text=message_data.content or ""))
    message = Message(author=Author(role=Role.ASSISTANT), content=content)

    if channel:
        message.with_channel(channel=channel.value)
    return message


def tool_call_output_message(
    message_data: ToolCallOutputParamChat,
    tool_calls: Dict[str, AssistantToolCallParamChat],
) -> Message:
    call_id = message_data.tool_call_id
    tool_call = tool_calls.get(call_id)

    assert tool_call is not None, f"tool_call is None: {message_data.model_dump()}"
    function_name = tool_call.function.name
    if "python" not in function_name and "browser" not in function_name:
        function_name = f"functions.{function_name}"  # see above; dirty hack, address

    message = Message(
        author=Author(role=Role.TOOL, name=function_name),  # TODO
        content=[TextContent(text=message_data.content)],
    )
    message.with_channel(AdapterAssistantChannel.COMMENTARY.value)
    message.with_recipient(Role.ASSISTANT.value)
    return message


def map_tool_calls(
    params: AdapterCreateParamsChat,
) -> Dict[str, AssistantToolCallParamChat]:
    tool_calls: Dict[str, AssistantToolCallParamChat] = {}
    for i in params.messages:
        match i:
            case AssistantMessageParamChat():
                if i.tool_calls is not None:
                    for t in i.tool_calls:
                        tool_calls[t.id] = t
    return tool_calls


def parse_messages(params: AdapterCreateParamsChat) -> List[Message]:
    messages: List[Message] = []
    tool_calls = map_tool_calls(params)

    for i in params.messages:
        match i:
            case UserMessageParamChat():
                messages.append(user_message(i))
            case AssistantMessageParamChat():
                messages.append(assistant_message(i, tool_calls))
            case ToolCallOutputParamChat():
                messages.append(tool_call_output_message(i, tool_calls))
            case _:
                pass  # throw?
    return messages


def parse_instructions(params: AdapterCreateParamsChat) -> str:
    instructions = ""
    for message in params.messages or []:
        if isinstance(message, SystemMessageParamChat):
            instructions = message.content
        if isinstance(message, DeveloperMessageParamChat):
            if not instructions:
                instructions = message.content
            else:
                instructions += f"\n\n{message.content}"
            break
    return instructions


def map_input_tools(
    params: AdapterCreateParamsChat,
) -> List[AdapterConversationInputTool]:
    tools = []
    for tool in params.tools or []:
        match tool:
            case AdapterFunctionToolParamChat():
                tool = AdapterConversationInputTool(
                    name=tool.function.name,
                    parameters=tool.function.parameters,
                    strict=tool.function.strict,
                    type=tool.type,
                    description=tool.function.description,
                )
                tools.append(tool)
            case AdapterCustomToolParamChat():
                fmt = None
                if tool.custom.format:
                    if tool.custom.format.type == "grammar":
                        fmt = CustomToolInputFormatGrammar(
                            definition=tool.custom.format.definition,
                            syntax=tool.custom.format.syntax,
                            type=tool.custom.format.type,
                        )
                    else:
                        fmt = CustomToolInputFormatText(
                            type=tool.custom.format.type or "text"
                        )

                tool = AdapterConversationInputTool(
                    name=tool.custom.name,
                    type=tool.type,
                    description=tool.custom.description or "",
                    format=fmt,
                )
            case _:
                raise NotImplementedError(f"Unsupported tool type: {type(tool)}")
    return tools


def build_message_list_chat(
    params: AdapterCreateParamsChat,
) -> AdapterConversationInputs:
    instructions = parse_instructions(params)
    messages = parse_messages(params)
    tools = map_input_tools(params)
    reasoning = params.reasoning or AdapterReasoningParam()

    conversation_inputs = AdapterConversationInputs(
        instructions=instructions,
        messages=messages,
        tools=tools,  # TODO
        reasoning=reasoning,  # TODO
    )
    return conversation_inputs
