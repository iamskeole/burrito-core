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
    load_harmony_encoding,
)

from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython

from burrito.common.config import settings
from burrito.common.utils import yyyymmdd, simple_markdown_renderer
from burrito.prompts.model_identity import MODEL_IDENTITY
from burrito.types.adapter import (
    AdapterConversationChannel,
    AdapterConversationInputs,
    AdapterConversationInputTool,
    AdapterCreateParams,
    AdapterCreateParamsChat,
    AdapterCreateParamsResponses,
)

from burrito.types.adapter.adapter_browser_tool_param import (
    AdapterBrowserToolParamChat,
    AdapterBrowserToolParamResponses,
)
from burrito.types.adapter.adapter_python_tool_param import (
    AdapterPythonToolParamChat,
    AdapterPythonToolParamResponses,
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


# TODO: decide whether to allow caller to change vs. increment dev msg
def build_system_message(
    inputs: AdapterConversationInputs,
    python_tool: Optional[BurritoPython],
    browser_tool: Optional[BurritoBrowser],
) -> Message:
    channel_config = ChannelConfig(
        valid_channels=[
            AdapterConversationChannel.ANALYSIS.value,
            AdapterConversationChannel.COMMENTARY.value,
            AdapterConversationChannel.FINAL.value,
        ],
        channel_required=True,
    )

    sys_message = (
        SystemContent.new()
        .with_model_identity(MODEL_IDENTITY.get(settings.MODEL_IDENTITY, "").strip())
        .with_conversation_start_date(yyyymmdd())
        .with_reasoning_effort(ReasoningEffort[inputs.reasoning.effort.upper()])  # type: ignore
        .with_channel_config(channel_config)
    )

    if python_tool is not None:
        sys_message = sys_message.with_tools(python_tool.tool_config)
    if browser_tool is not None:
        sys_message = sys_message.with_tools(browser_tool.tool_config)

    msg = Message.from_role_and_content(Role.SYSTEM, sys_message)
    return msg


def build_developer_message(inputs: AdapterConversationInputs) -> Message:
    instructions = inputs.instructions or ""
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
                tools.append(
                    ToolDescription.new(
                        tool.name, tool.description or "", tool.parameters
                    )
                )
    if tools:
        dev_message = dev_message.with_function_tools(tools)
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
    inputs: AdapterConversationInputs,
    python_tool: Optional[BurritoPython],
    browser_tool: Optional[BurritoBrowser],
) -> Conversation:
    system_message = build_system_message(inputs, python_tool, browser_tool)
    messages = [
        system_message,
        build_developer_message(inputs),
        *prune_reasoning(inputs.messages),  # unpack result of prune_reasoning
    ]
    conversation = build_conversation_from_messages(messages)
    return conversation


def resolve_python_tool(params: AdapterCreateParams) -> Optional[BurritoPython]:
    has_default = settings.IS_PYTHON_TOOL_ENABLED
    backend = settings.PYTHON_BACKEND
    should_enable = False

    # first, we check whether caller explicitly asks for capability
    # reasoning here being if caller builds tools, they should own explicitly
    # enabling capability by adding tool to tools list
    for tool in params.tools or []:
        match tool:
            case AdapterPythonToolParamChat() | AdapterPythonToolParamResponses():
                backend = tool.backend or settings.PYTHON_BACKEND
                should_enable = True
                break
            case _:
                continue

    # special case where caller has NO tools, we enable IF settings enable
    if not params.tools and has_default:
        should_enable = True

    # special case where config set up to override always enable
    if settings.IS_PYTHON_TOOL_ALWAYS_ENABLED:
        should_enable = True

    # if neither passes, we do NOT enable tool
    if not should_enable:
        return

    tool = BurritoPython(backend)
    return tool


def resolve_browser_tool(params: AdapterCreateParams) -> Optional[BurritoBrowser]:
    has_default = settings.IS_BROWSER_TOOL_ENABLED
    should_enable = False

    # first, we check whether caller explicitly asks for capability
    # reasoning here being if caller builds tools, they should own explicitly
    # enabling capability by adding tool to tools list
    for tool in params.tools or []:
        match tool:
            case AdapterBrowserToolParamChat() | AdapterBrowserToolParamResponses():
                should_enable = tool.web_search_enabled
                break
            case _:
                continue

    # special case where caller has NO tools, we enable IF settings enable
    if not params.tools and has_default:
        should_enable = True

    # special case where config set up to override always enable
    if settings.IS_BROWSER_TOOL_ALWAYS_ENABLED:
        should_enable = True

    # if neither passes, we do NOT enable tool
    if not should_enable:
        return

    tool = BurritoBrowser()
    return tool


def build_conversation_from_params(
    params: AdapterCreateParams, extra_messages: Optional[List[Message]]
) -> tuple[
    Conversation,
    AdapterConversationInputs,
    Optional[BurritoPython],
    Optional[BurritoBrowser],
]:
    assert isinstance(
        params,
        (
            AdapterCreateParamsChat,
            AdapterCreateParamsResponses,
        ),
    ), f"Unsupported params type: {type(params)}."
    match params:
        case AdapterCreateParamsResponses():
            inputs = build_message_list_responses(params)
        case AdapterCreateParamsChat():
            inputs = build_message_list_chat(params)

    tools: List[AdapterConversationInputTool] = []

    python_tool = resolve_python_tool(params)
    browser_tool = resolve_browser_tool(params)

    if python_tool:
        tools.append(
            AdapterConversationInputTool(
                name=python_tool.tool_config.name,
                description=python_tool.tool_config.description,
                type="python",
            )
        )
    if browser_tool:
        tools.append(
            AdapterConversationInputTool(
                name=browser_tool.tool_config.name,
                description=browser_tool.tool_config.description,
                type="browser",
            )
        )

    inputs.tools = tools + inputs.tools if inputs.tools else tools
    conversation = build_conversation_history(inputs, python_tool, browser_tool)
    if extra_messages:
        conversation.messages.extend(extra_messages)
    return (conversation, inputs, python_tool, browser_tool)


# TODO: if no developer message BUT! tools, create developer message with just tool definitions
# (see api_server.py in gpt-oss reference implementation)
def render_conversation_for_completion(
    conversation: Conversation, is_on_init: bool = False
) -> list[int]:
    # NOTE: render_conversation_for_completion doesn't always handle pruning
    # of reasoning correctly, so conversation.messages coming into it are always
    # manually pruned inside build_conversation_history => *prune_reasoning(...)
    tokens_for_completion = ENCODING.render_conversation_for_completion(
        conversation=conversation, next_turn_role=Role.ASSISTANT
    )

    if is_on_init and settings.DEBUG_PROMPT:
        dec = ENCODING.decode(tokens_for_completion)
        print(simple_markdown_renderer(dec))
        print(
            "prompt length: "
            f"t={len(tokens_for_completion):,} tokens, "
            f"c={len(dec):,} characters."
        )
    return tokens_for_completion
