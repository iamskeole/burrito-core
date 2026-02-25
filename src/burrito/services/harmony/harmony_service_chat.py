from __future__ import annotations

from typing import Dict, List

from openai_harmony import Author, Content, Message, Role, TextContent

from burrito.types.adapter import (
    AdapterAssistantChannel,
    AdapterConversationInputs,
    AdapterConversationInputTool,
    AdapterCreateParamsChat,
    AdapterReasoningParam,
)
from burrito.types.adapter.adapter_browser_tool_param import (
    AdapterBrowserToolParamChat,
)
from burrito.types.adapter.adapter_create_params_chat import (
    AssistantMessageParamChat,
    AssistantToolCallParamChat,
    ContentPartImageUrl,
    ContentPartText,
    DeveloperMessageParamChat,
    SystemMessageParamChat,
    ToolCallOutputParamChat,
    UserMessageParamChat,
)
from burrito.types.adapter.adapter_custom_tool_param import (
    AdapterCustomToolParamChat,
    CustomToolInputFormatGrammar,
    CustomToolInputFormatText,
)
from burrito.types.adapter.adapter_function_tool_param import (
    AdapterFunctionToolParamChat,
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
                    pass  # throw? tbd, only text supported by gpt-oss
                case _:
                    pass  # throw?
    else:
        pass  # throw?

    message = Message(author=Author(role=Role.USER), content=content)
    return message


def assistant_message(
    message_data: AssistantMessageParamChat,
    tool_calls: Dict[str, AssistantToolCallParamChat],
) -> list[Message]:
    messages: list[Message] = []
    author = Author(role=Role.ASSISTANT)
    # content: List[Content] = []
    # channel = None
    # recipient = None

    if message_data.reasoning_content:
        content: list[Content] = [TextContent(text=message_data.reasoning_content)]
        channel = AdapterAssistantChannel.ANALYSIS.value
        message = Message(author=author, content=content)
        message.with_channel(channel)
        messages.append(message)

    if message_data.tool_calls:
        for tc in message_data.tool_calls:
            tool_call = tool_calls.get(tc.id)
            assert tool_call is not None, "Tool call can not be none."
            tool_name = tool_call.function.name
            is_native_tool = "python" in tool_name or "browser" in tool_name
            prefix = "" if is_native_tool else "functions."
            recipient = f"{prefix}{tool_name}"
            content = [TextContent(text=tool_call.function.arguments)]
            message = Message(author=author, content=content)
            message.with_channel(AdapterAssistantChannel.COMMENTARY.value)
            message.with_recipient(recipient)
            messages.append(message)

    if message_data.content and isinstance(message_data.content, str):
        content: list[Content] = [TextContent(text=message_data.content)]
        channel = AdapterAssistantChannel.FINAL.value
        message = Message(author=author, content=content)
        message.with_channel(channel)
        messages.append(message)

    if message_data.content and isinstance(message_data.content, list):
        content = [TextContent(text=i.text or "") for i in message_data.content]
        channel = AdapterAssistantChannel.FINAL.value
        message = Message(author=author, content=content)
        message.with_channel(channel)
        messages.append(message)

    if len(messages) == 0:
        raise ValueError("Should not happen.")
    return messages


def tool_call_output_message(
    message_data: ToolCallOutputParamChat,
    tool_calls: Dict[str, AssistantToolCallParamChat],
) -> Message:
    call_id = message_data.tool_call_id
    tool_call = tool_calls.get(call_id)

    assert tool_call is not None, f"tool_call is None: {message_data.model_dump()}"
    message = Message(
        author=Author(role=Role.TOOL, name=f"functions.{tool_call.function.name}"),
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
                parsed = assistant_message(i, tool_calls)
                messages += parsed
            case ToolCallOutputParamChat():
                messages.append(tool_call_output_message(i, tool_calls))
            case _:
                pass  # throw?
    return messages


def parse_instructions(params: AdapterCreateParamsChat) -> str:
    instructions = ""
    for message in params.messages or []:
        match message:
            case SystemMessageParamChat() | DeveloperMessageParamChat():
                if isinstance(message.content, str):
                    instructions += f"\n{message.content}"
                else:
                    for c in message.content:
                        instructions += f"\n{c.text}"
            case _:
                pass
    return instructions


# TODO: handle tool_choice from params, eg auto, specific etc
def parse_tools(
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
                tools.append(tool)
            case AdapterBrowserToolParamChat():
                continue  # we handle native browser separately
            case _:
                raise NotImplementedError(f"Unsupported tool type: {type(tool)}")
    return tools


def build_message_list_chat(
    params: AdapterCreateParamsChat,
) -> AdapterConversationInputs:
    instructions = parse_instructions(params)
    messages = parse_messages(params)
    tools = parse_tools(params)
    reasoning = AdapterReasoningParam(effort=params.reasoning_effort)

    conversation_inputs = AdapterConversationInputs(
        instructions=instructions,
        messages=messages,
        tools=tools,
        reasoning=reasoning,
    )
    return conversation_inputs
