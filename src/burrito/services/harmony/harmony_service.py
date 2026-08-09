from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional, Union

from openai_harmony import (
    Author,
    ChannelConfig,
    Conversation,
    DeveloperContent,
    HarmonyEncodingName,
    Message,
    ReasoningEffort,
    RenderConversationConfig,
    Role,
    SystemContent,
    TextContent,
    ToolDescription,
    load_harmony_encoding,
)

from burrito.common.config import settings
from burrito.common.utils import get_prompt, is_valid_date, yyyymmdd
from burrito.services.harmony.harmony_service_chat import build_message_list_chat
from burrito.services.harmony.harmony_service_messages import (
    build_message_list_messages,
)
from burrito.services.harmony.harmony_service_responses import (
    build_message_list_responses,
)
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython
from burrito.types.conversation_enums import ConversationChannel
from burrito.types.conversation_inputs import ConversationInputs, ConversationToolParam
from burrito.types.tool_param_browser import (
    ToolParamBrowserChat,
    ToolParamBrowserResponses,
)
from burrito.types.tool_param_python import (
    ToolParamPythonChat,
    ToolParamPythonResponses,
)
from burrito.types.wire_api_params import WireApiParams
from burrito.types.wire_api_params_chat import WireApiParamsChat
from burrito.types.wire_api_params_messages import (
    ToolParam,
    ToolParamBrowserMessages,
    WireApiParamsMessages,
)
from burrito.types.wire_api_params_responses import WireApiParamsResponses

REASONING = {
    "high": ReasoningEffort.HIGH,
    "medium": ReasoningEffort.MEDIUM,
    "low": ReasoningEffort.LOW,
}

ENCODING = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
STOP_TOKENS = ENCODING.stop_tokens_for_assistant_actions()
STOP_WORDS = [ENCODING.decode([i]) for i in STOP_TOKENS]

TIME_DETECT_RE = re.compile(
    r"""
       (?P<hour>\d{1,2})                # <hour>            (keep)
       :\d{2}                           # :<minute>         (ignore)
       :\d{2}                           # :<second>         (ignore)
       (?:\.\d+)?                       # optional .<ms>    (ignore)
       (?P<ampm>\s*(?:AM|PM|am|pm))?    # optional AM/PM    (keep)
       """,
    re.VERBOSE,
)

# Replacement:  <hour>:00:00  +  the captured AM/PM (if any)
TIME_REPLACE_RE = r"\g<hour>:00:00\g<ampm>"


PLACEHOLDER_BROWSER = BurritoBrowser()
PLACEHOLDER_PYTHON = BurritoPython(is_placeholder=True)


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


def get_conversation_start_date() -> Optional[str]:
    sys_date_config = settings.SYSTEM_MESSAGE_DATE_CONFIG
    if sys_date_config == "off":
        sys_date = None
    elif sys_date_config == "auto":
        # we default to server timezone to mitigate midnight crossing between user / model
        # assuming user self-hosts model on a server in the same time zone as their client
        sys_date = yyyymmdd(in_utc=False)
    elif sys_date_config == "auto-utc":
        sys_date = yyyymmdd(in_utc=True)

    # 🐉 HIC SVNT DRACONES 🐉
    # meant to keep inputs consistent across days for consistent outputs if running evals
    # as the (natural) change in date WILL lead to different outputs;
    # careful with mistakenly leaving this on as it will probably mess up web searches
    elif sys_date_config != "off" and is_valid_date(sys_date_config):
        sys_date = settings.SYSTEM_MESSAGE_DATE_CONFIG
    else:
        sys_date = None  # should not happen
    return sys_date


def build_system_message(
    inputs: ConversationInputs,
    python_tool: Optional[Union[BurritoPython, str]],
    browser_tool: Optional[Union[BurritoBrowser, str]],
) -> Message:
    channels_w_tools = [
        ConversationChannel.ANALYSIS.value,
        ConversationChannel.COMMENTARY.value,
        ConversationChannel.FINAL.value,
    ]
    channels_no_tools = [
        ConversationChannel.ANALYSIS.value,
        ConversationChannel.FINAL.value,
    ]
    channel_config = ChannelConfig(
        valid_channels=channels_w_tools if inputs.tools else channels_no_tools,
        channel_required=True,
    )
    conv_date = get_conversation_start_date()

    try:
        identity = get_prompt(f"model_identity_{settings.MODEL_IDENTITY}")
    except FileNotFoundError:
        identity = get_prompt("model_identity_default")

    sys_message = (
        SystemContent.new()
        .with_model_identity(identity)
        .with_reasoning_effort(ReasoningEffort[inputs.reasoning.effort.upper()])  # type: ignore
        .with_channel_config(channel_config)
    )

    if conv_date is not None:
        sys_message = sys_message.with_conversation_start_date(conv_date)
    if python_tool is not None:
        sys_message = sys_message.with_tools(PLACEHOLDER_PYTHON.tool_config)
    if browser_tool is not None:
        sys_message = sys_message.with_tools(PLACEHOLDER_BROWSER.tool_config)

    msg = Message.from_role_and_content(Role.SYSTEM, sys_message)
    return msg


def build_developer_message(inputs: ConversationInputs) -> Optional[Message]:
    instructions = inputs.instructions or ""
    if not instructions and not inputs.tools:
        return
    if settings.CLEANUP_HIGH_PRECISION_PROMPT_TIMESTRINGS:
        instructions = TIME_DETECT_RE.sub(TIME_REPLACE_RE, instructions)
    dev_message = DeveloperContent.new().with_instructions(instructions)

    tools = []
    for tool in inputs.tools or []:
        match tool.type:
            case "function":
                tools.append(
                    ToolDescription.new(
                        tool.name, tool.description or "", tool.parameters
                    )
                )
            case "custom":
                # TODO: do this properly, if we decide to support
                # this is dirty and doesn't doo too much good
                # figure out a way to ENFORCE the grammar during inference
                # does vllm support this? i think llamacpp does on the fly, but check vllm
                t = ToolDescription.new(
                    tool.name, tool.description or "", tool.parameters
                )
                if tool.format is not None and tool.format.type == "grammar":
                    t.description += (
                        f"\nGRAMMAR SYNTAX: {tool.format.syntax}"
                        f"\nGRAMMAR DEFINITION: {tool.format.definition}"
                    )
                tools.append(t)
    if tools:
        dev_message = dev_message.with_function_tools(tools)
    return Message.from_role_and_content(Role.DEVELOPER, dev_message)


def build_assistant_message(text: str, channel: str) -> Message:
    return Message(
        author=Author(role=Role.ASSISTANT),
        content=[TextContent(text=text)],
        channel=channel,
    )


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


def prune_reasoning(messages: List[Message]) -> list[Message]:
    if len(messages) == 0:
        return messages

    if not settings.PRUNE_REASONING:
        return messages

    pruned: List[Message] = []
    # FIXME: harmony doesn't seem to handle pruning corretly at least some of the
    # time, not sure when / why, so we roll our own implementation defensively

    # find the index of the last assistant message on the "final" channel, which
    # is any message from the assistant that isn't a reasoning item;
    # we iterate backwards for efficiency
    last_assistant_ix = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        is_assistant = msg.author.role == Role.ASSISTANT
        is_reasoning = msg.channel == ConversationChannel.ANALYSIS.value
        is_final = msg.channel == ConversationChannel.FINAL.value
        has_recipient = msg.recipient is not None

        # is_reasoning and has_recipient a bit defensive, but probabilistic sampling!
        if is_assistant and is_final and not is_reasoning and not has_recipient:
            last_assistant_ix = i
            break

    is_in_tool_sequence = messages[-1].author.role == Role.TOOL

    for ix, message in enumerate(messages):
        is_reasoning = (
            message.author.role == Role.ASSISTANT
            and message.channel == ConversationChannel.ANALYSIS.value
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


def get_prompt_cache_messages(messages: List[Message]) -> List[Message]:
    have_user = False
    out = []
    for message in messages:
        if have_user:
            break
        match message.author.role:
            case Role.SYSTEM:
                out.append(message)
            case Role.DEVELOPER:
                out.append(message)
            case Role.TOOL:
                out.append(message)
            case Role.USER:
                out.append(message)
                have_user = True
    return out


def build_conversation_from_messages(messages: List[Message]) -> Conversation:
    return Conversation.from_messages(messages)


def build_conversation_history(
    inputs: ConversationInputs,
    python_tool: Optional[Union[BurritoPython, str]],
    browser_tool: Optional[Union[BurritoBrowser, str]],
) -> Conversation:
    messages = [build_system_message(inputs, python_tool, browser_tool)]
    dev_message = build_developer_message(inputs)

    # special case where no instructions AND no tools -> None
    if dev_message:
        messages.append(dev_message)

    messages += prune_reasoning(inputs.messages)
    # messages = [
    #     system_message,
    #     build_developer_message(inputs),
    #     *prune_reasoning(inputs.messages),  # unpack result of prune_reasoning
    # ]
    conversation = build_conversation_from_messages(messages)
    return conversation


def resolve_python_tool(params: WireApiParams) -> Optional[Union[BurritoPython, str]]:
    is_available = settings.IS_PYTHON_TOOL_AVAILABLE
    if not is_available:
        return
    should_enable = False

    # first, we check whether caller explicitly asks for capability
    # reasoning here being if caller builds tools, they should own explicitly
    # enabling capability by adding tool to tools list
    for tool in params.tools or []:
        match tool:
            case ToolParamPythonChat() | ToolParamPythonResponses():
                should_enable = True
                break
            case _:
                continue

    # special case where caller has NO tools, we enable IF settings enable
    # if not params.tools and is_available:
    #     should_enable = True

    # special case where config set up to override always enable
    if settings.IS_PYTHON_TOOL_ALWAYS_ENABLED:
        should_enable = True

    # if neither passes, we do NOT enable tool
    if not should_enable:
        return

    tool = "init-on-use"  # BurritoPython()
    return tool


def resolve_browser_tool(params: WireApiParams) -> Optional[Union[BurritoBrowser, str]]:
    is_available = settings.IS_BROWSER_TOOL_AVAILABLE
    if not is_available:
        return
    should_enable = False

    # first, we check whether caller explicitly asks for capability
    # reasoning here being if caller builds tools, they should own explicitly
    # enabling capability by adding tool to tools list
    for tool in params.tools or []:
        match tool:
            case ToolParamBrowserChat() | ToolParamBrowserResponses():
                should_enable = tool.external_acess or tool.web_search_enabled
                break

            # we use tool names to enable native browser
            # but in harmony_service_anthropic we disable claude code tools
            # since they are allover the place
            case ToolParam():
                if tool.name in ["WebFetch", "WebSearch"]:
                    should_enable = True

            # special case as the only tool, claude code harness
            # starts a new conversation with just web_search as tool,
            # then asks the model to search for `topic`
            # so we use this as a signal to toggle native browser on
            case ToolParamBrowserMessages():
                should_enable = True
            case _:
                continue

    # special case where caller has NO tools, we enable IF settings enable
    # if not params.tools and is_available:
    #     should_enable = True

    # special case where config set up to override always enable
    if settings.IS_BROWSER_TOOL_ALWAYS_ENABLED:
        should_enable = True

    # if neither passes, we do NOT enable tool
    if not should_enable:
        return

    tool = "init-on-use"  # BurritoBrowser()
    return tool


# TODO: figure out if / how we can support structured outputs (eg grammar, json)
# TODO: handle tool_choice from params, eg auto, specific etc;
# also, parallel (don't think it's possible? autoregressive)?
# TODO: investiagate whether we can support custom tools
# harmony only seems to support defining regular function tools
# with name, description, params; no special formatting instructions
# for custom tools, so even if we implemented schemas and code, model
# may not be trained to use them?
def build_conversation_from_params(
    params: WireApiParams, extra_messages: Optional[List[Message]]
) -> tuple[
    Conversation,
    ConversationInputs,
    Optional[Union[BurritoPython, str]],
    Optional[Union[BurritoBrowser, str]],
]:
    assert isinstance(
        params,
        (
            WireApiParamsChat,
            WireApiParamsResponses,
            WireApiParamsMessages,
        ),
    ), f"Unsupported params type: {type(params)}."
    match params:
        case WireApiParamsResponses():
            inputs = build_message_list_responses(params)
        case WireApiParamsChat():
            inputs = build_message_list_chat(params)
        case WireApiParamsMessages():
            inputs = build_message_list_messages(params)

    tools: List[ConversationToolParam] = []

    python_tool = resolve_python_tool(params)
    browser_tool = resolve_browser_tool(params)

    if python_tool is not None:
        tools.append(
            ConversationToolParam(
                name=PLACEHOLDER_PYTHON.tool_config.name,
                description=PLACEHOLDER_PYTHON.tool_config.description,
                type="python",
            )
        )
    if browser_tool is not None:
        tools.append(
            ConversationToolParam(
                name=PLACEHOLDER_BROWSER.tool_config.name,
                description=PLACEHOLDER_BROWSER.tool_config.description,
                type="browser",
            )
        )

    inputs.tools = tools + inputs.tools if inputs.tools else tools
    conversation = build_conversation_history(inputs, python_tool, browser_tool)
    if extra_messages:
        conversation.messages.extend(extra_messages)
    return (conversation, inputs, python_tool, browser_tool)


def render_conversation_for_completion(
    conversation: Conversation,
    is_on_init: bool = False,
    prefill_tokens: List[int] = [],
) -> list[int]:
    config = RenderConversationConfig(
        auto_drop_analysis=settings.PRUNE_REASONING
    )
    prompt_tokens = ENCODING.render_conversation_for_completion(
        conversation=conversation, next_turn_role=Role.ASSISTANT, config=config
    )
    tokens_for_completion = prompt_tokens + prefill_tokens

    if is_on_init and settings.DEBUG_PROMPT:
        dec = ENCODING.decode(tokens_for_completion)
        print(dec)
        print(
            "prompt length: "
            f"t={len(tokens_for_completion):,} tokens, "
            f"c={len(dec):,} characters."
        )
    return tokens_for_completion
