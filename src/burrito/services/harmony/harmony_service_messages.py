import json
from typing import Dict, List, Optional

from openai_harmony import (
    Author,
    Message,
    Role,
    TextContent,
)

from burrito.types.conversation_enums import (
    ConversationChannel,
    ConversationReasoningEffort,
)
from burrito.types.conversation_inputs import (
    ConversationInputs,
    ConversationReasoningParam,
    ConversationToolParam,
)
from burrito.types.wire_api_params_messages import (
    ContentBlockText,
    ContentBlockToolUse,
    ContentParam,
    ToolParam,
    ToolParamBrowserMessages,
    WireApiParamsMessages,
)


def user_message(
    input: ContentParam, tool_calls: Dict[str, ContentBlockToolUse]
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
                maybe_loop = []
                if isinstance(i.content, str):
                    maybe_loop.append(i.content)
                if isinstance(i.content, list):
                    for msg in i.content:
                        if not isinstance(msg, ContentBlockText):
                            continue
                        maybe_loop.append(msg.text)

                for txt in maybe_loop:
                    message = Message(author=author, content=[TextContent(text=txt)])  # type: ignore
                    message.with_channel(ConversationChannel.COMMENTARY.value)
                    message.with_recipient(Role.ASSISTANT.value)
                    messages.append(message)
    return messages


def assistant_message(input: ContentParam) -> Optional[List[Message]]:
    if input.role != "assistant":
        return
    messages: List[Message] = []
    author = Author(role=Role.ASSISTANT)
    if isinstance(input.content, str):
        messages.append(
            Message(
                author=author,
                content=[TextContent(text=input.content)],
                channel=ConversationChannel.FINAL.value,
            )
        )
    else:
        for i in input.content:
            channel = None
            recipient = None
            if i.type == "text":
                text = i.text
                channel = ConversationChannel.FINAL
            if i.type == "thinking":
                text = i.thinking
                channel = ConversationChannel.ANALYSIS
            if i.type == "tool_use":
                text = json.dumps(i.input)
                recipient = i.name
                channel = ConversationChannel.COMMENTARY

            # should not happen, tool_result message sent as user message
            if i.type == "tool_result":
                pass

            message = Message(author=author, content=[TextContent(text=text)])  # type: ignore
            if channel:
                message.with_channel(channel=channel.value)
            if recipient:
                is_native_tool = "python" in recipient or "browser" in recipient
                prefix = "" if is_native_tool else "functions."
                recipient_with_prefix = f"{prefix}{recipient}"
                message.with_recipient(recipient_with_prefix)
            messages.append(message)
    return messages


def parse_messages(inputs: List[ContentParam]) -> List[Message]:
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


def parse_tools(params: WireApiParamsMessages) -> List[ConversationToolParam]:
    tools: List[ConversationToolParam] = []
    for tool in params.tools or []:
        match tool:
            case ToolParam():
                # claude code at least has a weird way of fetching pages
                # seems to either call an api or use some curl-type fetch
                # then issues another call to the model to process
                # the raw html content; which is awful for token efficiency
                if tool.name in ["WebFetch"]:
                    continue

                # we disable WebSearch as it conflicts with native browser.search
                # and claude code implementation seems very specific to an opaque
                # api we can't replicate, leading to inference terminating early
                # sometimes (as well as creating a new conversation context just
                # instructing the model to search for topic)
                if tool.name in ["WebSearch"]:
                    continue
                t = ConversationToolParam(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.input_schema,
                    type="function",
                )
                tools.append(t)

            # special case for the actual web search tool that claude probably calls
            # this does nothing in the claude code harness, so probably
            # expected to call anthripic apis for results, hence we disable
            # so we can use native browser.search as a shim
            case ToolParamBrowserMessages():
                continue
            case _:
                continue
    return tools


def parse_instructions(params: WireApiParamsMessages) -> str:
    instructions = ""
    if not params.system:
        return instructions

    if isinstance(params.system, str):
        return params.system

    # x-anthropic-billing-header: cc_version=2.1.37.0d9; cc_entrypoint=cli; cch=d0108;
    # header that changes the VERY first message in any conversation, eg
    # cch=d018 changes with every subsequent message, which means prompt caching
    # cannot work; possible to disable by setting CLAUDE_CODE_ATTRIBUTION_HEADER=0
    # in .claude/settings.json, but keeping defensive validation in place just in case
    # CC decides to always include that since overhead is low
    instructions = "\n".join(
        [i.text for i in params.system if "x-anthropic-billing-header" not in i.text]
    )
    return instructions


def parse_reasoning(params: WireApiParamsMessages) -> ConversationReasoningParam:
    budget_tokens = 0
    if params.thinking and params.thinking.budget_tokens:
        budget_tokens = params.thinking.budget_tokens

    # best effort guesstimate of thinking budget vs. level
    if budget_tokens >= 20000:
        reasoning_effort = "high"
    elif budget_tokens >= 10000:
        reasoning_effort = "medium"
    else:
        reasoning_effort = "low"

    effort = ConversationReasoningEffort(reasoning_effort)
    reasoning = ConversationReasoningParam(effort=effort)
    return reasoning


def build_message_list_messages(params: WireApiParamsMessages) -> ConversationInputs:
    instructions = parse_instructions(params)
    messages = parse_messages(params.messages)
    tools = parse_tools(params)
    reasoning = parse_reasoning(params)
    conversation_inputs = ConversationInputs(
        instructions=instructions, messages=messages, tools=tools, reasoning=reasoning
    )
    return conversation_inputs
