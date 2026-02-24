from typing import TYPE_CHECKING, List, Optional

from openai_harmony import StreamableParser, StreamState

from burrito.common.logger import FastAPILogger
from burrito.services.harmony import SPECIAL_TOKENS
from burrito.types.adapter import (
    AdapterAssistantChannel,
    AdapterCompletionToken,
    AdapterConversationState,
    AdapterToolType,
)

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler

from burrito.common.config import settings


def is_created(parser: StreamableParser) -> bool:
    return len(parser.tokens) == 1 and parser.state == StreamState.HEADER


def is_in_progress(parser: StreamableParser) -> bool:
    return len(parser.tokens) in [2] and parser.state == StreamState.HEADER


def is_reasoning(parser: StreamableParser) -> bool:
    # producing reasoning tokens
    match_channel = parser.current_channel == AdapterAssistantChannel.ANALYSIS.value
    match_recipient = parser.current_recipient is None
    return match_channel and match_recipient


def is_reasoning_end(
    parser: StreamableParser, tokens: List[AdapterCompletionToken]
) -> bool:
    # reasoning done
    # last token == <|end|>
    # expecting <|start|>assistant<|channel>(commentary|final)
    last_token_id = tokens[-1].id if tokens else -1
    match_token = last_token_id == SPECIAL_TOKENS.END.id
    match_state = parser.state == StreamState.EXPECT_START
    return len(parser.messages) == 1 and match_state and match_token


# what do we do with it though? do we output on the final channel,
# so deafult to same label as output text?
# that should technically put it on the output channel i think
def is_preamble(parser: StreamableParser) -> bool:
    match_recipient = parser.current_recipient is None
    match_channel = parser.current_channel == AdapterAssistantChannel.COMMENTARY.value
    return match_channel and match_recipient


def is_tool_input(parser: StreamableParser) -> bool:
    # sometimes model calls tools (correctly) on analysis channel, eg.:
    # '<|channel|>analysis<|message|>
    # So the repository uses Poetry script entry points: burrito-dev and burrito.
    # We need to mention those.\n\nAlso there is a pre-commit hook perhaps?
    # Search for .pre-commit-config.<|end|>
    # <|start|>assistant<|channel|>analysis to=functions.shell<|message|>
    # {"command":["bash","-lc","ls -R | grep pre"],"timeout": 10000}
    # <|call|>'
    match_recipient = parser.current_recipient is not None
    match_channel = parser.current_channel in [
        AdapterAssistantChannel.ANALYSIS.value,
        AdapterAssistantChannel.COMMENTARY.value,
    ]
    return match_recipient and match_channel


def is_tool_input_start(parser: StreamableParser) -> bool:
    is_input = is_tool_input(parser)
    if not is_input:
        # header is done, now building actual tool input so no content yet
        return False
    return parser.last_content_delta is None


def is_tool_call(tokens: List[AdapterCompletionToken]) -> bool:
    last_token_id = tokens[-1].id if tokens else -1
    match_token = last_token_id == SPECIAL_TOKENS.CALL.id
    if match_token:
        return True
    return False


def is_output(parser: StreamableParser) -> bool:
    return parser.current_channel == AdapterAssistantChannel.FINAL.value


def is_return(tokens: List[AdapterCompletionToken]) -> bool:
    last_token_id = tokens[-1].id if tokens else -1
    match_token = last_token_id == SPECIAL_TOKENS.RETURN.id
    if match_token:
        return True
    return False


def is_native_tool(parser: StreamableParser) -> bool:
    messages = parser.messages
    last_message = messages[-1] if messages else None
    last_recipient = last_message.recipient if last_message else None
    last_channel = last_message.channel if last_message else None

    this_recipient = parser.current_recipient
    this_channel = parser.current_channel

    match_this_recipient = this_recipient in [
        AdapterToolType.BROWSER.value,
        AdapterToolType.PYTHON.value,
    ] or (this_recipient and this_recipient.startswith("browser."))
    match_last_recipient = last_recipient in [
        AdapterToolType.BROWSER.value,
        AdapterToolType.PYTHON.value,
    ] or (last_recipient and last_recipient.startswith("browser."))

    match_this_channel = this_channel in [
        AdapterAssistantChannel.ANALYSIS.value,
        AdapterAssistantChannel.COMMENTARY.value,
    ]
    match_last_channel = last_channel in [
        AdapterAssistantChannel.ANALYSIS.value,
        AdapterAssistantChannel.COMMENTARY.value,
    ]
    match_recipient = bool(match_this_recipient or match_last_recipient)
    match_channel = bool(match_this_channel or match_last_channel)
    return match_recipient and match_channel


def is_native_tool_input_start(parser: StreamableParser) -> bool:
    return is_tool_input_start(parser) and is_native_tool(parser)


def is_native_tool_input(parser: StreamableParser) -> bool:
    return is_tool_input(parser) and is_native_tool(parser)


def is_native_tool_call(
    parser: StreamableParser, tokens: List[AdapterCompletionToken]
) -> bool:
    return is_tool_call(tokens) and is_native_tool(parser)


class TransitionHandler:
    def __init__(self, manager: "AdapterStateHandler"):
        self.manager = manager

        self.reasoning_loops = 0

        self.log_id = manager.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"{self.log_id} | {__name__}"}

    def map_state(self) -> AdapterConversationState:
        parser = self.manager.parser
        messages = parser.messages
        tokens = self.manager.response_tokens
        prev_recipient = messages[-1].recipient if messages else None
        this_recipient = parser.current_recipient
        recipient = this_recipient or prev_recipient or ""
        is_native_tool = self.manager.tool_handler._is_native_tool(recipient)

        if is_created(parser):
            return AdapterConversationState.CREATED
        elif is_in_progress(parser):
            return AdapterConversationState.IN_PROGRESS
        elif is_reasoning(parser):
            return AdapterConversationState.REASONING
        elif is_reasoning_end(parser, tokens):
            return AdapterConversationState.REASONING_END
        elif is_preamble(parser):
            return AdapterConversationState.PREAMBLE
        elif is_tool_input_start(parser):
            if is_native_tool:
                return AdapterConversationState.NATIVE_TOOL_INPUT_START
            return AdapterConversationState.TOOL_INPUT_START
        elif is_tool_input(parser):
            if is_native_tool:
                return AdapterConversationState.NATIVE_TOOL_INPUT
            return AdapterConversationState.TOOL_INPUT
        elif is_tool_call(tokens):
            if is_native_tool:
                return AdapterConversationState.NATIVE_TOOL_CALL
            return AdapterConversationState.TOOL_CALL
        elif is_output(parser):
            return AdapterConversationState.OUTPUT_TEXT
        elif is_return(tokens):
            return AdapterConversationState.COMPLETED
        else:
            return AdapterConversationState.TRANSITION

    # TODO: maybe allow functions without the functions. namespace? map it back in tool handler if it's a valid tool?
    def _is_valid_transition(self, new_state: AdapterConversationState) -> bool:
        manager = self.manager
        tool_handler = manager.tool_handler
        parser = manager.parser
        messages = parser.messages
        last_message = messages[-1] if messages else None
        last_recipient = last_message.recipient if last_message else None
        current_recipient = parser.current_recipient
        channel = last_message.channel if last_message else None
        self.manager.response_buffer

        if new_state == AdapterConversationState.REASONING:
            self.reasoning_loops += 1

        if self.reasoning_loops >= settings.MAX_REASONING_LOOPS:
            self.reasoning_loops = 0
            self.logger.warning(
                "Invalid output: max reasoning loops.",
                extra=self.log_extra,
            )
            manager._add_recovery_message(
                "**Invalid output**: you seem to be stuck inside the analysis channel.\n"
                "Valid channels: analysis, commentary, final. "
                "Channel must be included for every message. "
                "Calls to these tools must go to the commentary channel: 'functions'. "
            )
            return False

        if new_state == AdapterConversationState.NATIVE_TOOL_DONE:
            return True

        state_tool_input_start = AdapterConversationState.TOOL_INPUT_START
        state_reasoning = AdapterConversationState.REASONING
        state_tool_call = AdapterConversationState.TOOL_CALL
        state_preamble = AdapterConversationState.PREAMBLE
        state_completed = AdapterConversationState.COMPLETED

        channel_analysis = AdapterAssistantChannel.ANALYSIS.value
        channel_commentary = AdapterAssistantChannel.COMMENTARY.value
        channel_final = AdapterAssistantChannel.FINAL.value

        # sometimes assistant will use tool name as channel, so we catch that before
        # wasting tokens to complete the full command
        # <|channel|>analysis<|message|>Check file.<|end|>
        # <|start|>assistant<|channel|>bash to=functions.shell<|channel|>commentary<|message|>{"command":["bash","-lc","sed -n '1,200p' TODO.md"]}<|return|>
        if messages and channel not in [
            channel_analysis,
            channel_commentary,
            channel_final,
        ]:
            self.logger.warning(
                f"Invalid output: bad channel `{channel}`.",
                extra=self.log_extra,
            )
            manager._add_recovery_message(
                "**Invalid output**: bad channel\n"
                "Valid channels: analysis, commentary, final. "
                "Channel must be included for every message. "
                "Calls to these tools must go to the commentary channel: 'functions'. "
                f"You are trying to output on: '{channel}'."
            )
            return False

        if new_state == state_tool_call:
            self.logger.debug(
                (f"calling tool `{last_recipient or parser.current_recipient}`."),
                extra=self.log_extra,
            )
        # TODO: check whether this is redundant with tool_handler._is_valid_tool?
        if new_state == state_tool_input_start and not tool_handler.is_valid(
            current_recipient
        ):
            return False

        if new_state == state_tool_call and not tool_handler.is_valid(last_recipient):
            return False  # reduntant with above, <|call|> is at end of input

        # 1. regression into reasoning state;
        # ok, model recovers by itself.. most of the time;
        # we keep validation for future reference
        if new_state == state_reasoning and channel == channel_analysis:
            if tool_handler.is_valid(last_recipient, new_state):
                return True
            return True

        # 2. tool call without prior input
        # NOTE: monitor, does it still happen or fixed with tool recovery msg?
        if new_state == state_tool_call and channel != channel_commentary:
            if tool_handler.is_valid(last_recipient, new_state):
                return True
            self.logger.warning(
                "invalid state: assistant calling a tool without prior input",
                extra=self.log_extra,
            )
            return True  # it's ok to send on any channel since we flag it?

        # 3. preamble, unclear what to do with it so we just log for now
        # NOTE: see harmony docs, sometime assistant may decide to issue
        # a summary of what it will do next inside the analysis channel, which,
        # according to docs, SHOULD be shown to users
        if new_state == state_preamble:
            if tool_handler.is_valid(last_recipient, new_state):
                return True
            self.logger.warning(
                "invalid state: assistant entered preamble state",
                extra=self.log_extra,
            )
            return True
        # 4. bad channel or return token
        # llama.cpp issue mostly; tool calls on return channel or transition
        # without end token eg: analysis -> <|end|> -> commentary (missing end)
        if new_state == state_completed and channel != channel_final:
            self.logger.warning(
                f"invalid state: assistant trying to return outside final channel, on {channel}.\n{self.manager.response_buffer}",
                extra=self.log_extra,
            )
            last_token = manager.response_tokens[-1].text
            manager._add_recovery_message(
                "**Invalid output**: bad return token.\n"
                "- user messages must be issued on the 'final' channel "
                "and end in a <|return|> token.\n"
                "- calls to tools or functions must be issued on one of "
                "'analysis' or 'commentary' channels, include a namespace and "
                "recipient (e.g.: functions.shell) and end in a special <|call|> token.\n"
                "- transitional messages, if any, (eg.: analysis to commentary) must "
                "end in a special <|end|> token.\n"
                "You are trying to output the token "
                f"'{last_token}' on the channel '{channel}'."
            )
            return False
        return True

    def _update_state(self) -> AdapterConversationState:
        old_state = self.manager.parser_state
        new_state = self.map_state()
        is_transition = new_state != old_state

        if is_transition and not self._is_valid_transition(new_state):
            return AdapterConversationState.ERROR

        self.manager.parser_state = new_state
        return new_state

    async def transition(
        self,
        token: Optional[AdapterCompletionToken],
        state: Optional[AdapterConversationState] = None,  # handle native tool done
    ):
        old_state = self.manager.parser_state
        new_state = state or self._update_state()

        if new_state == AdapterConversationState.ERROR:
            return self.manager._recover_state()

        if new_state != old_state:
            self.logger.debug(
                f"state change: {old_state.value:<18} -> {new_state.value}",
                extra=self.log_extra,
            )

            for plugin in self.manager._active_plugins_by_state.get(old_state, []):
                await plugin.on_exit_state(old_state)
            for plugin in self.manager._active_plugins_by_state.get(new_state, []):
                await plugin.on_enter_state(new_state)

        if not token:
            return
        if token.is_special_token:
            return
        for plugin in self.manager._active_plugins_by_state.get(new_state, []):
            await plugin.on_token(token)
