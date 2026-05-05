from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from anthropic.types.message import Message as AnthropicMessage
from openai.types.completion import Completion
from openai.types.responses.response import Response
from openai_harmony import (
    Conversation,
    HarmonyError,
    Message,
    Role,
    StreamableParser,
    StreamState,
)
from pydantic import BaseModel

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import (
    get_prompt,
    lark_to_gbnf,
    render_terminal_glyph,
    unix_timestamp_in_ms,
    wire_api_label_from_params,
)
from burrito.handlers.repetition_handler import RepetitionHandler
from burrito.handlers.token_handler import (
    normalize_completion_token,
)
from burrito.handlers.tool_handler import ToolHandler
from burrito.handlers.transition_handler import TransitionHandler
from burrito.plugins import BasePlugin
from burrito.plugins.chat import (
    ContextManagerPluginChat,
    NativeToolsPluginChat,
    OutputTextPluginChat,
    ReasoningTextPluginChat,
    ToolInputPluginChat,
)
from burrito.plugins.messages import (
    ContextManagerPluginMessages,
    NativeToolsPluginMessages,
    OutputTextPluginMessages,
    ReasoningTextPluginMessages,
    ToolInputPluginMessages,
)
from burrito.plugins.responses import (
    ContextManagerPluginResponses,
    NativeToolsPluginResponses,
    OutputTextPluginResponses,
    ReasoningTextPluginResponses,
    ToolInputPluginResponses,
)
from burrito.routes.metrics import (
    generation_duration_seconds,
    generation_duration_seconds_eval,
    generation_duration_seconds_prompt,
    generation_errors_total,
    generation_input_tokens,
    generation_output_tokens,
    generation_reasoning_tokens,
    generation_tool_call_tokens,
    generation_tool_calls,
    generation_total_tokens,
    generation_tps_eval,
    generation_tps_prompt,
)
from burrito.services.harmony import (
    ENCODING,
    SPECIAL_TOKENS,
    build_assistant_message,
    build_conversation_from_messages,
    build_conversation_from_params,
    build_user_message,
    get_prompt_cache_messages,
    render_conversation_for_completion,
)
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython
from burrito.types.conversation_enums import ConversationChannel, ConversationState
from burrito.types.conversation_error import ConversationError
from burrito.types.conversation_inputs import ConversationInputs
from burrito.types.conversation_token import ConversationToken
from burrito.types.patched_chat_completion import PatchedChatCompletion
from burrito.types.patched_chat_completion_chunk import PatchedChatCompletionChunk
from burrito.types.tool_param_custom import CustomToolInputFormatGrammar
from burrito.types.wire_api_params_chat import WireApiParamsChat
from burrito.types.wire_api_params_messages import WireApiParamsMessages
from burrito.types.wire_api_params_responses import WireApiParamsResponses

if TYPE_CHECKING:
    from .conversation_handler import ConversationHandler


class StateHandler:
    def __init__(self, manager: ConversationHandler, stream_to_caller: bool):
        self.manager = manager
        self.stream_to_caller = stream_to_caller

        self.conversation: Conversation
        self.conversation_inputs: ConversationInputs
        self.prompt_tokens: List[int]
        self.parser: StreamableParser

        self.completions: List[Completion] = []
        self.events: List[BaseModel] = []

        self.response_buffer: str = ""
        self.reasoning_buffer: str = ""
        self.native_tool_call_buffer: str = ""
        self.caller_tool_call_buffer: str = ""
        self.output_text_buffer: str = ""

        self.reasoning_interrupted = False
        self.last_parser_message_ix = 0

        # token stores for stats
        self.response_tokens: List[ConversationToken] = []
        self.reasoning_tokens: List[ConversationToken] = []
        self.preamble_tokens: List[ConversationToken] = []
        self.native_tool_input_tokens: List[ConversationToken] = []
        self.caller_tool_input_tokens: List[ConversationToken] = []
        self.output_text_tokens: List[ConversationToken] = []

        self.repetition_detector_reasoning: RepetitionHandler
        self.repetition_detector_non_reasoning: RepetitionHandler

        self.log_id: str = ""
        self.logger: logging.Logger
        self.log_extra: Dict[str, str]

        self.parser_channel: Optional[str] = None
        self.parser_state = ConversationState.INITIAL
        self.parser_message_count = 0
        self.sequence_number = 0
        self.output_index = -1
        self.is_done: bool = False

        self.output_object: Union[
            ConversationError,
            Response,
            List[Union[PatchedChatCompletionChunk, PatchedChatCompletion]],
            AnthropicMessage,
        ]

        self.plugins: List[BasePlugin]
        self._active_plugins_by_state: dict[str, list[BasePlugin]] = {}

        self.created_at = unix_timestamp_in_ms()
        self.recover_state_attempts = 0
        self.recovery_message: Optional[Message] = None
        self.extra_messages: List[Message] = []

        self.tool_handler: ToolHandler
        self.transition_handler: TransitionHandler

        self.break_ts_logs = []

        # python_tool, browser_tool = self._init_conversation()
        # self._init_tools(python_tool, browser_tool)
        # self._init_plugins()
        # self._init_logger()

    @classmethod
    # offload blocking init to a thread so requests don't block on init
    async def create(
        cls, manager: "ConversationHandler", stream_to_caller: bool
    ) -> "StateHandler":
        instance = cls(manager, stream_to_caller)
        await asyncio.to_thread(instance._setup_full_state)
        return instance

    def _setup_full_state(self):
        python_tool, browser_tool = self._init_conversation()
        self._init_tools(python_tool, browser_tool)
        self._init_plugins()
        self._init_logger()

    def get_prefill_tokens(self) -> List[int]:
        return [SPECIAL_TOKENS.CHANNEL.id]

    def _init_logger(self):
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": self.log_id}

    def _init_plugins(self):
        self.transition_handler = TransitionHandler(self)
        match self.manager.params:
            case WireApiParamsChat():
                self.plugins = [
                    ContextManagerPluginChat(self),
                    ReasoningTextPluginChat(self),
                    OutputTextPluginChat(self),
                    ToolInputPluginChat(self),
                    NativeToolsPluginChat(self),
                ]
            case WireApiParamsResponses():
                self.plugins = [
                    ContextManagerPluginResponses(self),
                    ReasoningTextPluginResponses(self),
                    OutputTextPluginResponses(self),
                    ToolInputPluginResponses(self),
                    NativeToolsPluginResponses(self),
                ]
            case WireApiParamsMessages():
                self.plugins = [
                    ContextManagerPluginMessages(self),
                    ReasoningTextPluginMessages(self),
                    OutputTextPluginMessages(self),
                    ToolInputPluginMessages(self),
                    NativeToolsPluginMessages(self),
                ]
            case _:
                return
        for plugin in self.plugins:
            for state in plugin.subscribed_states:
                self._active_plugins_by_state.setdefault(state, []).append(plugin)

    # this enables session-ish storage of python and browser tools
    # should help assistant if these tools are not stateless
    # (eg. assistant can reference previously opened pages or code cells)
    # bit hacky, hashing first few prompt messages will not work
    # if scaled horizontally, but we'll cross that bridge later
    def _init_tools(
        self,
        python_tool: Optional[Union[BurritoPython, str]],
        browser_tool: Optional[Union[BurritoBrowser, str]],
    ):
        session_handler = self.manager.session_handler
        params = self.manager.params

        if params.conversation and params.conversation.id:
            session_id = params.conversation.id
        elif params.prompt_cache_key:
            session_id = params.prompt_cache_key
        else:
            messages = get_prompt_cache_messages(self.conversation.messages)
            conversation = build_conversation_from_messages(messages)
            prompt_tokens = render_conversation_for_completion(conversation)
            prompt_text = ENCODING.decode(prompt_tokens)
            session_id = session_handler.hash_prompt(prompt_text)

        self.log_id = session_id

        # Use setdefault to avoid overwriting a live BurritoPython with "init-on-use".
        # If the cache already has a tool for this session (from a concurrent or
        # previous request), we reuse it instead of clobbering it with the sentinel.
        if python_tool is not None:
            python_tool = session_handler.python_tools.setdefault(
                self.log_id, python_tool
            )
        if browser_tool is not None:
            browser_tool = session_handler.browser_tools.setdefault(
                self.log_id, browser_tool
            )

        self.tool_handler = ToolHandler(
            self,
            python_tool,
            browser_tool,
        )

    def _init_conversation(
        self, extra_messages: Optional[List[Message]] = None
    ) -> tuple[Optional[BurritoPython | str], Optional[BurritoBrowser | str]]:
        params = self.manager.params
        conversation, inputs, python_tool, browser_tool = (
            build_conversation_from_params(params, extra_messages)
        )
        prefill_tokens = self.get_prefill_tokens()
        self.conversation = conversation
        self.conversation_inputs = inputs
        self.prompt_tokens = render_conversation_for_completion(
            conversation=self.conversation,
            is_on_init=True,
            prefill_tokens=prefill_tokens,
        )
        self.parser = StreamableParser(ENCODING, Role.ASSISTANT)
        for token in prefill_tokens:
            self.parser.process(token)

        # new detector instance so entropy checks reset, otherwise instant fail
        self.repetition_detector_reasoning = RepetitionHandler()
        self.repetition_detector_non_reasoning = RepetitionHandler()

        self.reasoning_buffer = ""
        self.native_tool_call_buffer = ""
        self.caller_tool_call_buffer = ""
        self.output_text_buffer = ""
        return (python_tool, browser_tool)

    async def put_close_marker(self):
        await self.manager.output_queue.put("data: [DONE]\n\n".encode())

    async def put_event(self, event: BaseModel):
        self.events.append(event)
        self.sequence_number += 1

        if not self.manager.stream_to_caller:
            return

        header = ""
        try:
            if hasattr(event, "type"):  # responses events
                header = f"event: {event.type}\n"  # type: ignore
            data = event.model_dump_json(indent=None)
            out = f"{header}data: {data}\n\n".encode()
            if settings.DEBUG_OUTGOING_EVENTS:
                self.logger.debug(out, extra=self.log_extra)
            await self.manager.output_queue.put(out)
        except Exception as e:
            print(e)

    # only responses supports streamed errors
    async def put_error(self, message: str, code: str):
        self.parser_state = ConversationState.ERROR
        self.is_done = True
        if hasattr(self.manager, "is_finished"):
            self.manager.is_finished.set()

        event = ConversationError(
            type="error",
            code=code,
            message=message,
            param=None,
            sequence_number=self.sequence_number,
        )
        self.output_object = event
        await self.put_event(event)

    def _add_recovery_message(self, text: str, is_assistant: bool = False):
        if not is_assistant:
            message = build_user_message(text, "BURRITO-HARNESS-SENTINEL")
        else:
            message = build_assistant_message(text, ConversationChannel.ANALYSIS.value)
        self.recovery_message = message

        if not settings.DEBUG_RESPONSE_BUFFER:
            return
        bfr = f"\n\n🚨🚨🚨\n\n{message.content[0].text}\n\n🚨🚨🚨\n\n"  # type: ignore
        self.response_buffer += bfr

    def update_state_with_tool_result(self, tool_result: List[Message]):
        if not tool_result:
            return
        self.manager._stop_stream()
        prev_messages = self.parser.messages
        prev_messages += tool_result

        for i in prev_messages:
            self.extra_messages.append(i)
        self._init_conversation(extra_messages=self.extra_messages)
        self.manager._init_stream()

    def _recover_state(self, partial_reasoning: str = ""):
        if self.recover_state_attempts >= settings.MAX_RECOVER_STATE_ATTEMPTS:
            raise RecursionError("Reached maximum state recover attempts.")
        self.response_buffer
        self.manager._stop_stream()
        self.parser_state = ConversationState.ERROR
        # TODO: check, should we default to no history since that will also lead to repetition?
        prev_messages = self.parser.messages  # we operate on rust view
        if partial_reasoning:
            msg_assistant = build_assistant_message(
                text=partial_reasoning,
                channel=self.parser.current_channel
                or ConversationChannel.ANALYSIS.value,
            )
            prev_messages.append(msg_assistant)

        if self.recovery_message:
            prev_messages.append(self.recovery_message)
            self.recovery_message = None

        for i in prev_messages:
            self.extra_messages.append(i)
        self._init_conversation(extra_messages=self.extra_messages)
        self.manager._init_stream()
        self.recover_state_attempts += 1
        # TODO: check this, any impact on non-repeat recovery triggers?
        # self.extra_messages = []  # clear extra messages (former recovery msgs)

    # 🐉 HIC SVNT DRACONES 🐉
    # we assume the user knows what they're doing when writing and wanting
    # to use a custom grammar; we convert user-specified grammar to gbnf
    # (if lark, eg openai Codex CLI apply_patch) and restart inference;
    # gbnf works for both llama.cpp and vLLM but probably openai uses lark
    # this was done mostly to make the latest codex cli work better otherwise
    # model spins its wheels a lot with string escaping until it figures out
    # how to properly format apply_patch inputs
    async def maybe_break_for_custom_tool_grammar(self):
        if self.parser_state != ConversationState.TOOL_INPUT_START:
            return

        tool = await self.tool_handler.get_tool_model_is_trying_to_call()
        if not tool:
            return

        if isinstance(tool, BurritoBrowser) or isinstance(tool, BurritoPython):
            return

        if not isinstance(tool.format, CustomToolInputFormatGrammar):
            return

        self.manager._stop_stream()
        prev_messages = self.parser.messages

        for i in prev_messages:
            self.extra_messages.append(i)

        _channel_token = ConversationChannel.COMMENTARY.value
        _message_token = SPECIAL_TOKENS.MESSAGE.text
        self._init_conversation(extra_messages=self.extra_messages)

        prefill = f"{_channel_token} to=functions.{tool.name}{_message_token}"
        enc = ENCODING.encode(prefill, allowed_special="all")

        for token in enc:
            self.parser.process(token)
            self.prompt_tokens.append(token)

        tkn, state = None, ConversationState.TOOL_INPUT_START
        await self.transition_handler.transition(tkn, state)
        grammar = lark_to_gbnf(tool.format.definition)
        self.manager._init_stream(grammar)

    def _store_token(self, token: ConversationToken):
        state = self.parser_state

        match state:
            case (
                ConversationState.INITIAL
                | ConversationState.CREATED
                | ConversationState.IN_PROGRESS
                | ConversationState.REASONING
                | ConversationState.PREAMBLE
                | ConversationState.REASONING_END
            ):
                self.reasoning_tokens.append(token)
                self.reasoning_buffer += token.text

            case (
                ConversationState.NATIVE_TOOL_INPUT_START
                | ConversationState.NATIVE_TOOL_INPUT
                | ConversationState.NATIVE_TOOL_CALL
            ):
                self.native_tool_input_tokens.append(token)
                self.native_tool_call_buffer += token.text
                self.tool_handler.current_call_buffer += token.text

                if state == ConversationState.NATIVE_TOOL_CALL:
                    active_call = self.tool_handler.tool_calls[-1]
                    active_call["content"] = self.tool_handler.current_call_buffer
                    self.tool_handler.current_call_buffer = ""
                    self.tool_handler.current_call_id = ""

            case (
                ConversationState.TOOL_INPUT_START
                | ConversationState.TOOL_INPUT
                | ConversationState.TOOL_CALL
            ):
                self.caller_tool_input_tokens.append(token)
                self.caller_tool_call_buffer += token.text

            case ConversationState.OUTPUT_TEXT | ConversationState.COMPLETED:
                self.output_text_tokens.append(token)
                self.output_text_buffer += token.text

        self.response_tokens.append(token)

        if settings.DEBUG_RESPONSE_BUFFER:
            self.response_buffer += token.text

    async def maybe_transition_created_state(self):
        # running eval on aime high reasoning, question 14, model starts
        # without a channel and transition gets fucked, so we guard here
        # also a reasoning tokens budget? at least with llama.cpp
        # backend, model keeps going close to context window max, and then
        # wants to return on non return channel, raising a state recovery
        # which eventually goes beyond context so overflow error in inference
        if len(self.response_tokens) > 0:
            return

        tkn, state = None, ConversationState.CREATED
        await self.transition_handler.transition(tkn, state)
        self.parser_state = state

    async def _break_non_reasoning_loop(self):
        ctx = ""
        ctx = get_prompt("monologue_break_non_reasoning_loop").format(
            native_tool_call_buffer=self.native_tool_call_buffer
            or "we did not call python or browser",
            caller_tool_call_buffer=self.caller_tool_call_buffer
            or "we did not call any tools",
            output_text_buffer=self.output_text_buffer or "we did not send to user",
        )
        if self.tool_handler.tools:
            msg = get_prompt("monologue_break_repetition_loop_w_tools")
        else:
            msg = get_prompt("monologue_break_repetition_loop_no_tools")
        self._add_recovery_message(msg, is_assistant=True)
        return self._recover_state(partial_reasoning=ctx)

    # NOTE: a bit hacky, may mess up tool calling, but shouldn't spend tens of thousands
    # of tokens for tools?
    # also, tradeoff / drawback = forces a prefill with the entire prompt + reasoning

    # TODO: figure out a way to do sentinel breaks if outside reasoing,
    # since if we just output, we may mess up tool calls the model could recover from
    async def _break_reasoning_loop(self):
        if self.tool_handler.tools:
            msg = get_prompt("monologue_break_repetition_loop_w_tools")
        else:
            msg = get_prompt("monologue_break_repetition_loop_no_tools")
        self._add_recovery_message(msg, is_assistant=True)
        reasoning_text = self.reasoning_buffer
        partial_reasoning = reasoning_text
        self.reasoning_buffer = ""
        return self._recover_state(partial_reasoning)

    async def maybe_break_non_reasoning_loop(self, token: ConversationToken):
        # may break some clients, eg they're probably not expecting output -> reasoning -> output
        # so we're giving the user a choice whether to activate this
        if not settings.BREAK_NON_REASONING_REPETITIONS:
            return

        # we handle reasoning loop breaks separately
        if self.parser_state in [
            ConversationState.INITIAL,
            ConversationState.CREATED,
            ConversationState.IN_PROGRESS,
            ConversationState.REASONING,
            ConversationState.PREAMBLE,
            ConversationState.REASONING_END,
            ConversationState.TRANSITION,
        ]:
            return

        is_repeating = self.repetition_detector_non_reasoning.process_new_token(token)
        if not is_repeating:
            return
        self.response_buffer
        if settings.DEBUG_STATE_ERRORS:
            self.logger.warning(
                "TRIGGER: maybe_break_non_reasoning_loop",
                extra=self.log_extra,
            )
        return await self._break_non_reasoning_loop()

    async def maybe_break_for_max_reasoning_tokens(self):
        if self.parser_state not in [
            ConversationState.REASONING,
            ConversationState.PREAMBLE,
        ]:
            return
        if self.reasoning_interrupted:
            return

        num_tokens = len(self.reasoning_tokens) + len(self.preamble_tokens)
        if num_tokens <= settings.MAX_REASONING_TOKENS:
            return
        if settings.DEBUG_STATE_ERRORS:
            self.logger.warning(
                "TRIGGER: maybe_break_for_max_reasoning_tokens",
                extra=self.log_extra,
            )
        await self._break_reasoning_loop()

    async def maybe_break_for_repeated_reasoning_text(self, token: ConversationToken):
        if self.parser_state not in [
            ConversationState.REASONING,
            ConversationState.PREAMBLE,
        ]:
            return
        self.response_buffer
        is_repeating = self.repetition_detector_reasoning.process_new_token(token)
        if not is_repeating:
            return
        if settings.DEBUG_STATE_ERRORS:
            self.logger.warning(
                "TRIGGER: maybe_break_for_repeated_reasoning_text",
                extra=self.log_extra,
            )
        await self._break_reasoning_loop()

    async def maybe_break_for_repeated_reasoning_loops(self):
        if self.transition_handler.reasoning_loops < settings.MAX_REASONING_LOOPS:
            return
        self.transition_handler.reasoning_loops = 0
        if settings.DEBUG_STATE_ERRORS:
            self.logger.warning(
                "TRIGGER: maybe_break_for_repeated_reasoning_loops",
                extra=self.log_extra,
            )
        await self._break_reasoning_loop()

    async def maybe_break_for_repeated_preamble_loops(self):
        if self.transition_handler.preamble_loops < settings.MAX_PREAMBLE_LOOPS:
            return
        self.transition_handler.preamble_loops = 0
        if settings.DEBUG_STATE_ERRORS:
            self.logger.warning(
                "TRIGGER: maybe_break_for_repeated_preamble_loops",
                extra=self.log_extra,
            )
        await self._break_reasoning_loop()

    async def maybe_break_inference_loop(self, token: ConversationToken):
        t0 = unix_timestamp_in_ms()
        await self.maybe_break_for_custom_tool_grammar()
        await self.maybe_break_for_repeated_reasoning_text(token)
        await self.maybe_break_for_repeated_reasoning_loops()
        await self.maybe_break_for_repeated_preamble_loops()
        await self.maybe_break_for_max_reasoning_tokens()
        await self.maybe_break_non_reasoning_loop(token)
        td = unix_timestamp_in_ms() - t0
        self.break_ts_logs.append(td)

    async def _process_completion(
        self, completion: Union[Completion, str]
    ) -> Union[ConversationToken, None]:
        if isinstance(completion, str):
            return

        await self.maybe_transition_created_state()

        token = normalize_completion_token(
            completion=completion,
            response_tokens=self.response_tokens,
            parser_channel=self.parser.current_channel,
            parser_recipient=self.parser.current_recipient,
        )

        parser_tokens = self.parser.tokens
        last_parser_token = parser_tokens[-1] if parser_tokens else -1

        if not token or token.id == -1:
            return

        # edge case where model emits constrain token with no tools, on final channel
        # which means it won't output a <|message|> token, which means parser
        # hangs in header state, which means it doesn't register the final channel
        # so we perform small brain surgery to convert <|constrain|> to <|message|>
        if token.id == SPECIAL_TOKENS.CONSTRAIN.id and not self.tool_handler.tools:
            token.id = SPECIAL_TOKENS.MESSAGE.id
            token.text = SPECIAL_TOKENS.MESSAGE.text

        # weird special case where assistant emitting same
        # special token (<|message|>  or <|channel|> ?) twice?
        # if so, we skip that token since we already added it?
        # also, sometimes happens when assistant regresses into reasoning,
        # so maybe that's a problem in the harmony implementation as well
        # i guess it's good that we catch it here and with try / except below
        # maybe good idea to transition state before parsing? but that depends
        # on parser state so kind of circular? but we catch it here AND in
        # state validation, so we should be good?
        if ENCODING.is_special_token(token.id) and token.id == last_parser_token:
            self.logger.error(
                "Bad token: back to back special token", extra=self.log_extra
            )
            return

        try:
            self.parser.process(token.id)
        except HarmonyError as e:
            if settings.DEBUG_HARMONY_ERRORS:
                self.logger.debug(f"{repr(e)}", extra=self.log_extra)
            # generic recovery message since it can be a variety of reasons,
            # - HarmonyError('unexpected tokens remaining in message header: List[str]')
            #   (rare, mostly cahght by validations)
            # - HarmonyError('Unknown role: assistant<|channel|>commentary')
            # - anything else?
            # msg = get_prompt("sentinel_bad_token_sequence").format(
            #     model_output=f"{repr(e.args[0])}"
            # )

            # repr-ing the harmony error sometimes dumps full assistant text
            # which is confusing so we use a generic message instead
            msg = get_prompt("sentinel_bad_token_sequence_generic")
            self._add_recovery_message(msg)
            return self._recover_state()

        # store AFTER parser.process so we only store valid tokens
        # in case this needs to be fed into reports / stats later
        # eg if we recover state, we don't count the "bad" tokens
        self.completions.append(completion)
        self._store_token(token)

        if self.parser.messages and self.parser.state == StreamState.EXPECT_START:
            self.conversation.messages.append(self.parser.messages[-1])
            self.tool_handler.patch_native_tool_recipient()
            self.parser_message_count += 1

        await self.transition_handler.transition(token)
        await self.tool_handler.maybe_call_native_tool()
        await self.maybe_break_inference_loop(token)

    def _log_stats(self):
        p_t, r_t = self.prompt_tokens, self.response_tokens
        if not r_t:
            return

        total_break_time = sum(self.break_ts_logs)
        mean_break_time = total_break_time / len(self.break_ts_logs)
        print(f"mean time to break logs = {mean_break_time:.8f} ms")
        print(f"total time to break logs = {total_break_time:.4f} ms")

        t_p = (r_t[0].created_at - self.created_at) / 1000
        t_e = (r_t[-1].created_at - r_t[0].created_at) / 1000
        t_t = t_p + t_e

        n_p, n_e = len(p_t), len(r_t)
        n_t = n_p + n_e
        n_r = len(self.reasoning_tokens)
        t_c = len(self.tool_handler.tool_calls)
        tps_p = n_p / t_p if t_p > 0 else 0
        tps_e = n_e / t_e if t_e > 0 else 0

        m = self.manager.params.model
        w = wire_api_label_from_params(self.manager.params)

        # formatters
        def fn(n):  # tokens: "105.0k" or "  215 "
            if n >= 1000:
                return f"{n / 1000:>5.1f}k"
            return f"{int(n):>5} "

        def ft(t):  # time: " 51.97s" or "  0.31s"
            return f"{t:>6.2f}s"

        def fs(s):  # speed: " 22.7k" or "   45 "
            if s >= 1000:
                return f"{s / 1000:>5.1f}k"
            return f"{int(s):>5} "

        w_blk = f"{w:<16}"

        # total block: "  35.9k ‣  51.97s (i:  1.48s ‣ o: 50.49s)"
        t_blk = f"{fn(n_t)} ‣ {ft(t_t)} (i:{ft(t_p)} ‣ o:{ft(t_e)})"

        # input block: "i:  33.6k ( 22.7k/s)"
        i_blk = f"i:{fn(n_p)} ({fs(tps_p)}/s)"

        # output block: "o:   2.3k (   45 /s)"
        o_blk = f"o:{fn(n_e)} ({fs(tps_e)}/s)"

        # tool call block ⚒ 🗜️ 🔧 🔨 🛠 ⚒️ 🧰 ⚙️
        c_blk = f"{render_terminal_glyph('🔧', '⚒')} {t_c:<2}"

        l_msg = f"{w_blk} • {t_blk} • {i_blk} ‣ {o_blk} • {c_blk}"

        self.logger.info(l_msg, extra={"log_id": self.log_id, "skip_module_name": True})
        # expose generation metrics to Prometheus

        generation_duration_seconds.labels(wire_api=w, model=m).observe(t_t)
        generation_duration_seconds_prompt.labels(wire_api=w, model=m).observe(t_p)
        generation_duration_seconds_eval.labels(wire_api=w, model=m).observe(t_e)

        generation_tps_prompt.labels(wire_api=w, model=m).observe(tps_p)
        generation_tps_eval.labels(wire_api=w, model=m).observe(tps_e)

        generation_total_tokens.labels(wire_api=w, model=m).inc(n_t)
        generation_input_tokens.labels(wire_api=w, model=m).inc(n_p)
        generation_output_tokens.labels(wire_api=w, model=m).inc(n_e)
        generation_reasoning_tokens.labels(wire_api=w, model=m).inc(n_r)
        for call in self.tool_handler.tool_calls:
            tn = call["tool"].name
            generation_tool_calls.labels(wire_api=w, model=m, tool_name=tn).inc()
            generation_tool_call_tokens.labels(wire_api=w, model=m, tool_name=tn).inc()

    def _cleanup_on_done(self, completion: Union[Completion, str]):
        self.is_done = isinstance(completion, str) and completion == "[DONE]"
        if not self.is_done:
            return
        self._log_stats()
        return self.response_buffer

    def _debug_completion(self, completion: Union[Completion, str]):
        if not settings.DEBUG_COMPLETIONS:
            return
        if isinstance(completion, str):
            self.logger.debug(completion)
        else:
            self.logger.debug(completion.choices[0])

    async def process_completion(self, completion: Union[Completion, Dict, str]):
        if isinstance(completion, dict):
            msg = f"Backend error: {completion.get('error')}"
            self.logger.error(msg, extra=self.log_extra)
            await self.put_error(msg, "ERR_BACKEND_EXCEPTION")
            self.is_done = True
            # increment generation error counter
            m = self.manager.params.model
            w = wire_api_label_from_params(self.manager.params)
            generation_errors_total.labels(wire_api=w, model=m).inc()
            return

        self._debug_completion(completion)
        await self._process_completion(completion)
        self._cleanup_on_done(completion)
