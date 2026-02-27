from __future__ import annotations

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
    render_terminal_glyph,
    unix_timestamp_in_ms,
    wire_api_label_from_params,
)
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
    build_conversation_from_messages,
    build_conversation_from_params,
    build_user_message,
    get_prompt_cache_messages,
    render_conversation_for_completion,
)
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython
from burrito.types.conversation_enums import ConversationState
from burrito.types.conversation_error import ConversationError
from burrito.types.conversation_inputs import ConversationInputs
from burrito.types.conversation_token import ConversationToken
from burrito.types.patched_chat_completion import PatchedChatCompletion
from burrito.types.patched_chat_completion_chunk import PatchedChatCompletionChunk
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

        # token stores for stats
        self.response_tokens: List[ConversationToken] = []
        self.reasoning_tokens: List[ConversationToken] = []
        self.preamble_tokens: List[ConversationToken] = []
        self.native_tool_input_tokens: List[ConversationToken] = []
        self.caller_tool_input_tokens: List[ConversationToken] = []
        self.output_text_tokens: List[ConversationToken] = []

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

        python_tool, browser_tool = self._init_conversation()

        self._init_tools(python_tool, browser_tool)
        self._init_plugins()
        self._init_logger()

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
        python_tool: Optional[BurritoPython],
        browser_tool: Optional[BurritoBrowser],
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
            session_id = session_handler.hash_text(prompt_text)

        self.log_id = session_id
        session_handler.set_python_tool(self.log_id, python_tool)
        session_handler.set_browser_tool(self.log_id, browser_tool)

        self.tool_handler = ToolHandler(
            self,
            python_tool=session_handler.get_python_tool(session_id),
            browser_tool=session_handler.get_browser_tool(session_id),
        )

    def _init_conversation(
        self, extra_messages: Optional[List[Message]] = None
    ) -> tuple[Optional[BurritoPython], Optional[BurritoBrowser]]:
        params = self.manager.params
        conversation, inputs, python_tool, browser_tool = (
            build_conversation_from_params(params, extra_messages)
        )
        self.conversation = conversation
        self.conversation_inputs = inputs
        self.prompt_tokens = render_conversation_for_completion(
            conversation=self.conversation, is_on_init=True
        )
        self.parser = StreamableParser(ENCODING, Role.ASSISTANT)
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

    def _add_recovery_message(self, text: str):
        message = build_user_message(text, "BURRITO-HARNESS-SENTINEL")
        self.recovery_message = message

        if not settings.DEBUG_RESPONSE_BUFFER:
            return
        bfr = f"\n\n🚨🚨🚨\n\n{message.content[0].text}\n\n🚨🚨🚨\n\n"  # type: ignore
        self.response_buffer += bfr

    def _update_state_with_tool_result(self, tool_result: List[Message]):
        if not tool_result:
            return
        self.manager._stop_stream()
        prev_messages = self.parser.messages
        prev_messages += tool_result

        for i in prev_messages:
            self.extra_messages.append(i)
        self._init_conversation(extra_messages=self.extra_messages)
        self.manager._init_stream()

    def _recover_state(self):
        if self.recover_state_attempts >= settings.MAX_RECOVER_STATE_ATTEMPTS:
            raise RecursionError("Reached maximum state recover attempts.")

        self.manager._stop_stream()
        self.parser_state = ConversationState.ERROR
        prev_messages = self.parser.messages  # we operate on rust view
        if self.recovery_message:
            prev_messages.append(self.recovery_message)
            self.recovery_message = None

        for i in prev_messages:
            self.extra_messages.append(i)
        self._init_conversation(extra_messages=self.extra_messages)
        self.manager._init_stream()
        self.recover_state_attempts += 1

    def _store_token(self, token: ConversationToken):
        state = self.parser_state

        match state:
            case (
                ConversationState.INITIAL
                | ConversationState.CREATED
                | ConversationState.IN_PROGRESS
                | ConversationState.REASONING
                | ConversationState.REASONING_END
            ):
                self.reasoning_tokens.append(token)

            case ConversationState.PREAMBLE:
                self.preamble_tokens.append(token)

            case (
                ConversationState.NATIVE_TOOL_INPUT_START
                | ConversationState.NATIVE_TOOL_INPUT
                | ConversationState.NATIVE_TOOL_CALL
            ):
                self.native_tool_input_tokens.append(token)

            case (
                ConversationState.TOOL_INPUT_START
                | ConversationState.TOOL_INPUT
                | ConversationState.TOOL_CALL
            ):
                self.caller_tool_input_tokens.append(token)

            case ConversationState.OUTPUT_TEXT | ConversationState.COMPLETED:
                self.output_text_tokens.append(token)

        self.response_tokens.append(token)

        if settings.DEBUG_RESPONSE_BUFFER:
            self.response_buffer += token.text

    async def _process_completion(
        self, completion: Union[Completion, str]
    ) -> Union[ConversationToken, None]:
        if isinstance(completion, str):
            return

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

        # NOTE: weird special case where assistant emitting same
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
            msg = get_prompt("sentinel_bad_token_sequence").format(
                model_output=f"{repr(e.args[0])}"
            )
            self._add_recovery_message(msg)
            return self._recover_state()

        # NOTE: moved AFTER parser.process so we only store valid tokens
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

    def _log_stats(self):
        p_t, r_t = self.prompt_tokens, self.response_tokens
        if not r_t:
            return

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
        return  # self.response_buffer

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
