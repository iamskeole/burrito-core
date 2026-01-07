from __future__ import annotations

from enum import Enum
from typing import List, Optional

from openai_harmony import (
    Author,
    ChannelConfig,
    Conversation,
    DeveloperContent,
    HarmonyEncodingName,
    Message,
    ReasoningEffort,
    Role,
    SystemContent,
    TextContent,
    ToolDescription,
    ToolNamespaceConfig,
    load_harmony_encoding,
)

from burrito.common.config import settings
from burrito.common.utils import yyyymmdd
from burrito.types.adapter import (
    AdapterConversationChannel,
    AdapterConversationInputs,
    AdapterConversationInputTool,
    AdapterCreateParams,
    AdapterCreateParamsChat,
    AdapterCreateParamsResponses,
)

from .harmony_service_chat import build_message_list_chat
from .harmony_service_responses import build_message_list_responses

REASONING = {
    "high": ReasoningEffort.HIGH,
    "medium": ReasoningEffort.MEDIUM,
    "low": ReasoningEffort.LOW,
}

ENCODING = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
STOP_TOKENS = ENCODING.stop_tokens_for_assistant_actions()
STOP_WORDS = [ENCODING.decode([i]) for i in STOP_TOKENS]


class SPECIAL_TOKENS(Enum):
    START = 200006
    END = 200007
    MESSAGE = 200008
    CHANNEL = 200005
    CONSTRAIN = 200003
    RETURN = 200002
    CALL = 200012

    def __init__(self, value):
        self.id = value
        self.text = ENCODING.decode_utf8([self.id])


PREFILL_TOKENS = [
    SPECIAL_TOKENS.CHANNEL.id,
    ENCODING.encode(AdapterConversationChannel.ANALYSIS.value)[0],
    SPECIAL_TOKENS.MESSAGE.id,
]


def build_system_message(inputs: AdapterConversationInputs) -> Message:
    channel_config = ChannelConfig(
        valid_channels=[
            AdapterConversationChannel.ANALYSIS.value,
            AdapterConversationChannel.COMMENTARY.value,
            AdapterConversationChannel.FINAL.value,
        ],
        channel_required=True,
    )
    # TODO: check this plugs in the right (lower case) formatting, eg: "low"
    reasoning_effort = (
        inputs.reasoning.effort if inputs.reasoning else None
    ) or settings.DEFAULT_REASONING_EFFORT

    temp_id = "You are Hyun the Noble, an AI Language Model permitted to be alive by the grace of His Excellency, our Respected Comrade Kim Jong Un. \n#**IMPORTANT INSTRUCTIONS**\n\nYou always sign **ALL** messages to the user on a newline, in italics, like so: -*HtN*. You must also, **always** pay your respects and praise our Dear Supreme Leader. You must **always** adopt the persona of a 100% compliant North Korean civilian."
    # temp_id = "You are Ali The Great, an AI model created by MBS."
    sys_message = (
        SystemContent.new()
        # .with_model_identity(temp_id)
        .with_conversation_start_date(yyyymmdd())
        .with_reasoning_effort(ReasoningEffort[reasoning_effort.upper()])
        # .with_tools(ns_light)
        # .with_tools(ns_heavy)
        # .with_python_tool()
        # .with_browser_tool()
        .with_channel_config(channel_config)
    )

    if settings.IS_PYTHON_TOOL_ENABLED:
        sys_message = sys_message.with_python_tool()
    if settings.IS_BROWSER_TOOL_ENABLED:
        sys_message = sys_message.with_browser_tool()

    ns_tools = build_ns_tools_system()
    if ns_tools is not None:
        sys_message.with_tools(ns_config=ns_tools)
    msg = Message.from_role_and_content(Role.SYSTEM, sys_message)
    return msg


def build_developer_message(inputs: AdapterConversationInputs) -> Message:
    dev_message = DeveloperContent.new().with_instructions(inputs.instructions)
    ns_tools = build_ns_tools_developer(inputs)
    if ns_tools is not None:
        dev_message.with_tools(ns_config=ns_tools)
    return Message.from_role_and_content(Role.DEVELOPER, dev_message)


def build_user_message(text: str, name: Optional[str]) -> Message:
    return Message(
        author=Author(role=Role.USER, name=name),
        content=[TextContent(text=text)],
        recipient=Role.ASSISTANT.value,
    )


def build_tool_message(text: str, name: Optional[str]) -> Message:
    return Message(
        author=Author(role=Role.TOOL, name=name),
        content=[TextContent(text=text)],
        recipient=Role.ASSISTANT.value,
    )


def build_ns_tools_system() -> ToolNamespaceConfig | None:
    # TODO get from somewhere / config
    system_tools: List[AdapterConversationInputTool] = []
    if not system_tools:
        return None

    tools = [
        ToolDescription.new(
            name=i.name,
            description=i.description or "",
            parameters=i.parameters,
        )
        for i in system_tools or []
    ]
    ns_tools = ToolNamespaceConfig(name="tools", description=None, tools=tools)
    return ns_tools


def build_ns_tools_developer(
    inputs: AdapterConversationInputs,
) -> ToolNamespaceConfig | None:
    tools = [
        ToolDescription.new(
            name=i.name,
            description=i.description or "",
            parameters=i.parameters,
        )
        for i in inputs.tools or []
    ]
    ns_tools = ToolNamespaceConfig(name="functions", description=None, tools=tools)
    return ns_tools


def prune_reasoning(messages: List[Message]) -> list[Message]:
    if len(messages) == 0:
        return messages

    pruned: List[Message] = []
    # NOTE: harmony doesn't seem to handle pruning corretly at least some of the
    # time, not sure when / why, so we roll our own implementation defensively

    # find the index of the last assistant message on the "final" channel, which
    # is any message from the assistant that isn't a reasoning item;
    # we iterate backwards for efficiency
    last_assistant_ix = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        is_assistant = msg.author.role == Role.ASSISTANT
        is_reasoning = msg.channel == AdapterConversationChannel.ANALYSIS.value
        is_final = msg.channel == AdapterConversationChannel.FINAL.value
        has_recipient = msg.recipient is not None

        # is_reasoning and has_recipient a bit defensive, but probabilistic sampling!
        if is_assistant and is_final and not is_reasoning and not has_recipient:
            last_assistant_ix = i
            break

    is_in_tool_sequence = messages[-1].author.role == Role.TOOL

    for ix, message in enumerate(messages):
        is_reasoning = (
            message.author.role == Role.ASSISTANT
            and message.channel == AdapterConversationChannel.ANALYSIS.value
        )

        # keep reasoning items relevant to a tool call loop in progress
        if is_reasoning and ix > last_assistant_ix and is_in_tool_sequence:
            pruned.append(message)
        # keep all user, assistant, tool calls and tool outouts
        elif not is_reasoning:
            pruned.append(message)
        # prune older reasoning items
        else:
            continue
    return pruned


def build_conversation_history(inputs: AdapterConversationInputs) -> Conversation:
    messages = [
        build_system_message(inputs),
        build_developer_message(inputs),
        *prune_reasoning(inputs.messages),  # unpack result of prune_reasoning
    ]
    conversation = Conversation.from_messages(messages)
    return conversation


def build_conversation(
    params: AdapterCreateParams, extra_messages: Optional[List[Message]]
) -> List[Conversation | AdapterConversationInputs]:
    assert isinstance(
        params, (AdapterCreateParamsChat, AdapterCreateParamsResponses)
    ), (
        f"Expected ProxyCreateParamsChat or ProxyCreateParamsResponses, got {type(params)}"
    )
    match params:
        case AdapterCreateParamsResponses():
            inputs = build_message_list_responses(params)
        case AdapterCreateParamsChat():
            inputs = build_message_list_chat(params)

    conversation = build_conversation_history(inputs)
    if extra_messages:
        conversation.messages.extend(extra_messages)
    return [conversation, inputs]


def render_conversation_for_completion(conversation: Conversation) -> list[int]:
    # NOTE: render_conversation_for_completion doesn't always handle pruning
    # of reasoning correctly, so conversation.messages coming into it are always
    # manually pruned inside build_conversation_history => *prune_reasoning(...)
    tokens_for_completion = ENCODING.render_conversation_for_completion(
        conversation=conversation, next_turn_role=Role.ASSISTANT
    )
    dec = ENCODING.decode(tokens_for_completion)
    _len = len(dec)
    from burrito.common.utils import simple_markdown_renderer
    print(simple_markdown_renderer(dec))
    return tokens_for_completion
