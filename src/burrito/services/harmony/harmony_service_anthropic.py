from typing import List, Dict, Optional
import json

from openai_harmony import (
    Author,
    Message,
    Role,
    Content,
    TextContent,
)

from burrito.types.adapter.adapter_create_params_anthropic import (
    AdapterCreateParamsAnthropic,
    AdapterInputParamMessageAnthropic,
    ContentBlockText,
    ContentBlockAssistantReasoning,
    ContentBlockImage,
    ContentBlockToolUse,
    ContentBlockToolResult,
    AdapterToolParamInputAnthropic,
    WebSearchToolParamAnthropic,
)
from burrito.types.adapter import (
    AdapterAssistantChannel,
    AdapterConversationInputs,
    AdapterConversationInputTool,
    AdapterReasoningParam,
    AdapterReasoningEffort,
)


def user_message(
    input: AdapterInputParamMessageAnthropic, tool_calls: Dict[str, ContentBlockToolUse]
) -> Optional[List[Message]]:
    if input.role != "user":
        return

    messages: List[Message] = []
    author = Author(role=Role.USER)
    if isinstance(input.content, str):
        messages.append(
            Message(author=author, content=[TextContent(text=input.content)])
        )
    else:
        for i in input.content:
            if i.type == "text":
                messages.append(
                    Message(author=author, content=[TextContent(text=i.text)])
                )
            if i.type == "tool_use":
                # should not happen, anthropic / claude code 
                # sends tool_use as assistant message
                continue

            # tool_result messages sent as user messages as of cc v2.1.37
            if i.type == "tool_result":
                tool_call_result = tool_calls.get(i.tool_use_id)
                if tool_call_result is None:
                    continue
                author = Author(
                    role=Role.TOOL, name=f"functions.{tool_call_result.name}"
                )
                message = Message(author=author, content=[TextContent(text=i.content)])
                message.with_channel(AdapterAssistantChannel.COMMENTARY.value)
                message.with_recipient(Role.ASSISTANT.value)
                messages.append(message)
    return messages


def assistant_message(
    input: AdapterInputParamMessageAnthropic,
) -> Optional[List[Message]]:
    if input.role != "assistant":
        return
    messages: List[Message] = []
    author = Author(role=Role.ASSISTANT)
    if isinstance(input.content, str):
        messages.append(
            Message(
                author=author,
                content=[TextContent(text=input.content)],
                channel=AdapterAssistantChannel.FINAL.value,
            )
        )
    else:
        for i in input.content:
            channel: AdapterAssistantChannel = None
            recipient: str = None
            if i.type == "text":
                text = i.text
                channel = AdapterAssistantChannel.FINAL
            if i.type == "thinking":
                text = i.thinking
                channel = AdapterAssistantChannel.ANALYSIS
            if i.type == "tool_use":
                text = json.dumps(i.input)
                recipient = i.name
                channel = AdapterAssistantChannel.COMMENTARY
            
            # should not happen, tool_result message sent as user message
            if i.type == "tool_result":
                pass

            message = Message(author=author, content=[TextContent(text=text)])
            if channel:
                message.with_channel(channel=channel.value)
            if recipient:
                message.with_recipient(recipient)
            messages.append(message)
    return messages


def parse_messages(inputs: List[AdapterInputParamMessageAnthropic]) -> List[Message]:
    messages: List[Message] = []

    tool_calls: Dict[str, ContentBlockToolUse] = {}
    for i in inputs:
        if isinstance(i.content, str):
            continue

        for c in i.content:
            if isinstance(c, ContentBlockToolUse):
                tool_calls[c.id] = c

    for i in inputs:
        match i.role:
            case "user":
                parsed = user_message(i, tool_calls)
                if parsed:
                    messages += parsed

            case "assistant":
                parsed = assistant_message(i)
                if parsed:
                    messages += parsed

            case _:
                continue
    return messages


def parse_tools(
    params: AdapterCreateParamsAnthropic,
) -> List[AdapterConversationInputTool]:
    tools: List[AdapterConversationInputTool] = []
    for tool in params.tools or []:
        match tool:
            case AdapterToolParamInputAnthropic():
                # claude code at least has a weird way of fetching pages
                # seems to either call an api or use some curl-type fetch
                # then issues another call to the model to do something
                # with the raw content; additionally, this messes up with
                # the native browser.open as it exposes two tools for the
                # same job; so we disable for now
                if tool.name in ["WebFetch"]:
                    continue

                # same for WebSearch, that sometimes triggers a web search
                # instead of a fetch when user (or assistant) wants to browse a page
                # so we just disable both functions to fall back on browser
                if tool.name in ["WebSearch"]:
                    continue
                t = AdapterConversationInputTool(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.input_schema,
                    type="function",
                )
                tools.append(t)
            case WebSearchToolParamAnthropic():
                continue  #
            case _:
                continue  # TODO WebFetchToolParam?
    return tools


def parse_instructions(params: AdapterCreateParamsAnthropic) -> str:
    instructions = ""
    if not params.system:
        return instructions

    if isinstance(params.system, str):
        return params.system

    instructions = "\n".join([i.text for i in params.system])
    return instructions


def parse_reasoning(params: AdapterCreateParamsAnthropic) -> AdapterReasoningParam:
    budget_tokens = 0
    if params.thinking and params.thinking.budget_tokens:
        budget_tokens = params.thinking.budget_tokens

    if budget_tokens >= 16000:
        reasoning_effort = "high"
    elif budget_tokens >= 8000:
        reasoning_effort = "medium"
    else:
        reasoning_effort = "low"

    reasoning = AdapterReasoningParam(
        effort=AdapterReasoningEffort(reasoning_effort)
    )
    return reasoning


def build_message_list_anthropic(
    params: AdapterCreateParamsAnthropic,
) -> AdapterConversationInputs:
    instructions = parse_instructions(params)
    messages = parse_messages(params.messages)
    tools = parse_tools(params)
    reasoning = parse_reasoning(params)

    conversation_inputs = AdapterConversationInputs(
        instructions=instructions, messages=messages, tools=tools, reasoning=reasoning
    )
    return conversation_inputs
