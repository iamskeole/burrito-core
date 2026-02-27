from typing import TYPE_CHECKING, List, Optional

from openai_harmony import StreamableParser, StreamState

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import get_prompt
from burrito.services.harmony import SPECIAL_TOKENS
from burrito.types.conversation_enums import ConversationChannel, ConversationState
from burrito.types.conversation_token import ConversationToken

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


def is_created(parser: StreamableParser) -> bool:
    return len(parser.tokens) == 1 and parser.state == StreamState.HEADER


def is_in_progress(parser: StreamableParser) -> bool:
    return len(parser.tokens) in [2] and parser.state == StreamState.HEADER


def is_reasoning(parser: StreamableParser) -> bool:
    # producing reasoning tokens
    match_channel = parser.current_channel == ConversationChannel.ANALYSIS.value
    match_recipient = parser.current_recipient is None
    return match_channel and match_recipient


def is_reasoning_end(parser: StreamableParser, tokens: List[ConversationToken]) -> bool:
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
    match_channel = parser.current_channel == ConversationChannel.COMMENTARY.value
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
        ConversationChannel.ANALYSIS.value,
        ConversationChannel.COMMENTARY.value,
    ]
    return match_recipient and match_channel


def is_tool_input_start(parser: StreamableParser) -> bool:
    is_input = is_tool_input(parser)
    if not is_input:
        # header is done, now building actual tool input so no content yet
        return False
    return parser.last_content_delta is None


def is_tool_call(tokens: List[ConversationToken]) -> bool:
    last_token_id = tokens[-1].id if tokens else -1
    match_token = last_token_id == SPECIAL_TOKENS.CALL.id
    if match_token:
        return True
    return False


def is_output(parser: StreamableParser) -> bool:
    return parser.current_channel == ConversationChannel.FINAL.value


def is_return(tokens: List[ConversationToken]) -> bool:
    last_token_id = tokens[-1].id if tokens else -1
    match_token = last_token_id == SPECIAL_TOKENS.RETURN.id
    if match_token:
        return True
    return False


class TransitionHandler:
    def __init__(self, manager: "StateHandler"):
        self.manager = manager

        self.reasoning_loops = 0

        self.log_id = manager.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": self.log_id}

    def map_state(self) -> ConversationState:
        parser = self.manager.parser
        messages = self.manager.parser.messages
        tokens = self.manager.response_tokens
        prev_recipient = messages[-1].recipient if messages else None
        this_recipient = parser.current_recipient
        recipient = this_recipient or prev_recipient or ""
        is_native_tool = self.manager.tool_handler._is_native_tool(recipient)

        if is_created(parser):
            return ConversationState.CREATED
        elif is_in_progress(parser):
            return ConversationState.IN_PROGRESS
        elif is_reasoning(parser):
            return ConversationState.REASONING
        elif is_reasoning_end(parser, tokens):
            return ConversationState.REASONING_END
        elif is_preamble(parser):
            return ConversationState.PREAMBLE
        elif is_tool_input_start(parser):
            if is_native_tool:
                return ConversationState.NATIVE_TOOL_INPUT_START
            return ConversationState.TOOL_INPUT_START
        elif is_tool_input(parser):
            if is_native_tool:
                return ConversationState.NATIVE_TOOL_INPUT
            return ConversationState.TOOL_INPUT
        elif is_tool_call(tokens):
            if is_native_tool:
                return ConversationState.NATIVE_TOOL_CALL
            return ConversationState.TOOL_CALL
        elif is_output(parser):
            return ConversationState.OUTPUT_TEXT
        elif is_return(tokens):
            return ConversationState.COMPLETED
        else:
            return ConversationState.TRANSITION

    def _is_valid_transition(self, new_state: ConversationState) -> bool:
        tool_handler = self.manager.tool_handler
        parser = self.manager.parser
        # we operate on the rust view since new messages may be building
        messages = self.manager.parser.messages
        last_message = messages[-1] if messages else None
        last_recipient = last_message.recipient if last_message else None
        current_recipient = parser.current_recipient
        channel = last_message.channel if last_message else None

        if new_state == ConversationState.REASONING:
            self.reasoning_loops += 1

        if self.reasoning_loops >= settings.MAX_REASONING_LOOPS:
            self.reasoning_loops = 0
            msg = get_prompt("sentinel_reasoning_loop")
            self.manager._add_recovery_message(msg)
            if settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    "Invalid output: max reasoning loops.",
                    extra=self.log_extra,
                )
            return False

        if new_state == ConversationState.NATIVE_TOOL_DONE:
            return True

        state_tool_input_start = ConversationState.TOOL_INPUT_START
        state_reasoning = ConversationState.REASONING
        state_tool_call = ConversationState.TOOL_CALL
        state_preamble = ConversationState.PREAMBLE
        state_completed = ConversationState.COMPLETED

        channel_analysis = ConversationChannel.ANALYSIS.value
        channel_commentary = ConversationChannel.COMMENTARY.value
        channel_final = ConversationChannel.FINAL.value

        # sometimes assistant will use tool name as channel, so we catch that before
        # wasting tokens to complete the full command
        # <|channel|>analysis<|message|>Check file.<|end|>
        # <|start|>assistant<|channel|>bash to=functions.shell<|channel|>commentary<|message|>{"command":["bash","-lc","sed -n '1,200p' TODO.md"]}<|return|>
        if messages and channel not in [
            channel_analysis,
            channel_commentary,
            channel_final,
        ]:
            msg = get_prompt("sentinel_bad_channel").format(channel=channel)
            self.manager._add_recovery_message(msg)
            if settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    f"Invalid output: bad channel `{channel}`.",
                    extra=self.log_extra,
                )
            return False

        if new_state == state_tool_call and settings.DEBUG_TOOL_CALLS:
            self.logger.debug(
                (f"calling tool `{last_recipient or parser.current_recipient}`."),
                extra=self.log_extra,
            )

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
            if settings.DEBUG_STATE_ERRORS:
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
            if settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    "assistant entered preamble state",
                    extra=self.log_extra,
                )
            return True
        # 4. bad channel or return token
        # llama.cpp issue mostly; tool calls on return channel or transition
        # without end token eg: analysis -> <|end|> -> commentary (missing end)
        if new_state == state_completed and channel != channel_final:
            last_token = self.manager.response_tokens[-1].text
            msg = get_prompt("sentinel_bad_return_token").format(
                token=last_token, channel=channel
            )
            self.manager._add_recovery_message(msg)
            if settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    (
                        "invalid state: assistant trying to return outside the `final` "
                        f"channel, on `{channel}`."
                    ),
                    extra=self.log_extra,
                )
            return False
        return True

    def _update_state(self) -> ConversationState:
        old_state = self.manager.parser_state
        new_state = self.map_state()
        is_transition = new_state != old_state

        if is_transition and not self._is_valid_transition(new_state):
            return ConversationState.ERROR

        self.manager.parser_state = new_state
        return new_state

    async def transition(
        self,
        token: Optional[ConversationToken],
        state: Optional[ConversationState] = None,  # handle native tool done
    ):
        old_state = self.manager.parser_state
        new_state = state or self._update_state()

        if new_state == ConversationState.ERROR:
            return self.manager._recover_state()

        if new_state != old_state:
            if settings.DEBUG_STATE_CHANGE:
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
