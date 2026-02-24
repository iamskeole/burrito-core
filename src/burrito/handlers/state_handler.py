from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from anthropic.types.message import Message as AnthropicMessage
from openai.types.completion import Completion
from openai.types.responses.response import Response
from pydantic import BaseModel

from burrito.types.adapter.adapter_chat_completion import AdapterChatCompletion
from burrito.types.adapter.adapter_chat_completion_chunk import (
    AdapterChatCompletionChunk,
)

if TYPE_CHECKING:
    from .conversation_handler import AdapterConversationHandler

from openai_harmony import (
    Conversation,
    HarmonyError,
    Message,
    Role,
    StreamableParser,
)

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid, unix_timestamp_in_ms
from burrito.handlers.token_handler import (
    normalize_completion_token,
)
from burrito.handlers.tool_handler import ToolHandler
from burrito.handlers.transition_handler import TransitionHandler
from burrito.plugins import BasePlugin
from burrito.plugins.anthropic import (
    ContextManagerPluginAnthropic,
    NativeToolsPluginAnthropic,
    OutputTextPluginAnthropic,
    ReasoningTextPluginAnthropic,
    ToolInputPluginAnthropic,
)
from burrito.plugins.chat import (
    ContextManagerPluginChat,
    NativeToolsPluginChat,
    OutputTextPluginChat,
    ReasoningTextPluginChat,
    ToolInputPluginChat,
)
from burrito.plugins.responses import (
    ContextManagerPluginResponses,
    NativeToolsPluginResponses,
    OutputTextPluginResponses,
    ReasoningTextPluginResponses,
    ToolInputPluginResponses,
)
from burrito.services.harmony import (
    ENCODING,
    build_conversation_from_params,
    build_user_message,
    render_conversation_for_completion,
)
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython
from burrito.types.adapter import (
    AdapterCompletionToken,
    AdapterConversationInputs,
    AdapterConversationState,
    AdapterCreateParamsAnthropic,
    AdapterCreateParamsChat,
    AdapterCreateParamsResponses,
    AdapterErrorEvent,
)


class AdapterStateHandler:
    def __init__(
        self, manager: AdapterConversationHandler, stream_to_caller: bool
    ):
        self.manager = manager
        self.stream_to_caller = stream_to_caller

        self.conversation: Conversation
        self.conversation_inputs: AdapterConversationInputs
        self.prompt_tokens: List[int]
        self.parser: StreamableParser

        self.completions: List[Completion] = []
        self.events: List[BaseModel] = []
        self.response_buffer: str = ""

        # token stores for stats
        self.response_tokens: List[AdapterCompletionToken] = []
        self.reasoning_tokens: List[AdapterCompletionToken] = []
        self.preamble_tokens: List[AdapterCompletionToken] = []
        self.native_tool_input_tokens: List[AdapterCompletionToken] = []
        self.caller_tool_input_tokens: List[AdapterCompletionToken] = []
        self.output_text_tokens: List[AdapterCompletionToken] = []

        self.log_id: str = ""
        self.logger: logging.Logger
        self.log_extra: Dict[str, str]

        self.parser_channel: Optional[str] = None
        self.parser_state = AdapterConversationState.INITIAL
        self.sequence_number = 0
        self.output_index = -1
        self.is_done: bool = False

        self.output_object: Union[
            AdapterErrorEvent,
            Response,
            List[Union[AdapterChatCompletionChunk, AdapterChatCompletion]],
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
        self.log_extra = {"log_id": f"{self.log_id} | {__name__}"}

    def _init_plugins(self):
        self.transition_handler = TransitionHandler(self)
        match self.manager.params:
            case AdapterCreateParamsChat():
                self.plugins = [
                    ContextManagerPluginChat(self),
                    ReasoningTextPluginChat(self),
                    OutputTextPluginChat(self),
                    ToolInputPluginChat(self),
                    NativeToolsPluginChat(self),
                ]
            case AdapterCreateParamsResponses():
                self.plugins = [
                    ContextManagerPluginResponses(self),
                    ReasoningTextPluginResponses(self),
                    OutputTextPluginResponses(self),
                    ToolInputPluginResponses(self),
                    NativeToolsPluginResponses(self),
                ]
            case AdapterCreateParamsAnthropic():
                self.plugins = [
                    ContextManagerPluginAnthropic(self),
                    ReasoningTextPluginAnthropic(self),
                    OutputTextPluginAnthropic(self),
                    ToolInputPluginAnthropic(self),
                    NativeToolsPluginAnthropic(self),
                ]
            case _:
                return
        for plugin in self.plugins:
            for state in plugin.subscribed_states:
                self._active_plugins_by_state.setdefault(state, []).append(
                    plugin
                )

    # NOTE: this enables session-ish storage of python and browser tools
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
            session_id = random_uuid()
            # messages = get_prompt_cache_messages(self.conversation.messages)
            # conversation = build_conversation_from_messages(messages)
            # prompt_tokens = render_conversation_for_completion(conversation)
            # prompt_text = ENCODING.decode(prompt_tokens)
            # session_id = session_handler.hash_text(prompt_text)

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
        self.parser_state = AdapterConversationState.ERROR
        self.is_done = True
        if hasattr(self.manager, "is_finished"):
            self.manager.is_finished.set()

        event = AdapterErrorEvent(
            type="error",
            code=code,
            message=message,
            param=None,
            sequence_number=self.sequence_number,
        )
        self.output_object = event
        await self.put_event(event)

    def _add_recovery_message(self, text: str):
        message = build_user_message(text, "HARNESS-SENTINEL-v1")
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
        self.parser_state = AdapterConversationState.ERROR
        prev_messages = self.parser.messages
        if self.recovery_message:
            prev_messages.append(self.recovery_message)
            self.recovery_message = None

        for i in prev_messages:
            self.extra_messages.append(i)
        self._init_conversation(extra_messages=self.extra_messages)
        self.manager._init_stream()
        self.recover_state_attempts += 1

    def _store_token(self, token: AdapterCompletionToken):
        state = self.parser_state

        match state:
            case (
                AdapterConversationState.INITIAL
                | AdapterConversationState.CREATED
                | AdapterConversationState.IN_PROGRESS
                | AdapterConversationState.REASONING
                | AdapterConversationState.REASONING_END
            ):
                self.reasoning_tokens.append(token)

            case AdapterConversationState.PREAMBLE:
                self.preamble_tokens.append(token)

            case (
                AdapterConversationState.NATIVE_TOOL_INPUT_START
                | AdapterConversationState.NATIVE_TOOL_INPUT
                | AdapterConversationState.NATIVE_TOOL_CALL
            ):
                self.native_tool_input_tokens.append(token)

            case (
                AdapterConversationState.TOOL_INPUT_START
                | AdapterConversationState.TOOL_INPUT
                | AdapterConversationState.TOOL_CALL
            ):
                self.caller_tool_input_tokens.append(token)

            case (
                AdapterConversationState.OUTPUT_TEXT
                | AdapterConversationState.COMPLETED
            ):
                self.output_text_tokens.append(token)

        self.response_tokens.append(token)

        if settings.DEBUG_RESPONSE_BUFFER:
            self.response_buffer += token.text

    async def _process_completion(
        self, completion: Union[Completion, str]
    ) -> Union[AdapterCompletionToken, None]:
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
        if (
            ENCODING.is_special_token(token.id)
            and token.id == last_parser_token
        ):
            self.logger.error(
                "Bad token: back to back special token", extra=self.log_extra
            )
            return

        try:
            self.parser.process(token.id)
        except HarmonyError as e:
            self.logger.error(
                f"_process_completion: {repr(e)}", extra=self.log_extra
            )
            # generic recovery message since it can be a variety of reasons,
            # - HarmonyError('unexpected tokens remaining in message header: List[str]')
            #   (rare, mostly cahght by validations)
            # - HarmonyError('Unknown role: assistant<|channel|>commentary')
            # - anything else?
            self._add_recovery_message(
                f"**Invalid output**: bad token sequence:\n{repr(e.args[0])}"
            )
            return self._recover_state()

        # NOTE: moved AFTER parser.process so we only store valid tokens
        # in case this needs to be fed into reports / stats later
        # eg if we recover state, we don't count the "bad" tokens
        self.completions.append(completion)
        self._store_token(token)

        await self.transition_handler.transition(token)
        await self.tool_handler.maybe_call_native_tool()

    def _log_stats(self):
        n_tokens_prompt = len(self.prompt_tokens)
        n_tokens_response = len(self.response_tokens)
        n_tokens_total = n_tokens_prompt + n_tokens_response

        first_token = self.response_tokens[0]
        last_token = self.response_tokens[-1]

        delta_pp = first_token.created_at - self.created_at
        delta_tg = last_token.created_at - first_token.created_at
        delta_total = (delta_pp + delta_tg) / 1000

        tps_pp = n_tokens_prompt / (delta_pp / 1000) if delta_pp else 0
        tps_tg = n_tokens_response / (delta_tg / 1000) if delta_tg else 0

        self.logger.debug(
            (
                f"{'prompt:':<12}"
                f"{delta_pp / 1000:>10,.2f}s"
                f"{n_tokens_prompt:>10,} tokens"
                f"{delta_pp / n_tokens_prompt:>10,.2f} ms/tok"
                f"{tps_pp:>10,.0f} tok/s"
            ),
            extra=self.log_extra,
        )
        self.logger.debug(
            (
                f"{'eval: ':<12}"
                f"{delta_tg / 1000:>10,.2f}s"
                f"{n_tokens_response:>10,} tokens"
                f"{delta_tg / n_tokens_response:>10,.2f} ms/tok"
                f"{tps_tg:>10,.0f} tok/s"
            ),
            extra=self.log_extra,
        )

        self.logger.debug(
            (
                f"{'total:':<12}{delta_total:>10,.2f}s{n_tokens_total:>10,} tokens"
            ),
            extra=self.log_extra,
        )

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

    async def process_completion(
        self, completion: Union[Completion, Dict, str]
    ):
        if isinstance(completion, dict):
            msg = f"Backend error: {completion.get('error')}"
            self.logger.error(msg, extra=self.log_extra)
            await self.put_error(msg, "ERR_BACKEND_EXCEPTION")
            self.is_done = True
            return

        self._debug_completion(completion)
        await self._process_completion(completion)
        self._cleanup_on_done(completion)
