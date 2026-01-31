from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from burrito.common.logger import FastAPILogger

if TYPE_CHECKING:
    from .conversation_handler import AdapterConversationHandler

from openai.types.completion import Completion
from openai.types.responses.response import Response

from burrito.types.adapter.adapter_chat_completion_chunk import (
    AdapterChatCompletionChunk,
)
from burrito.types.adapter.adapter_chat_completion import AdapterChatCompletion

from openai_harmony import (
    Conversation,
    HarmonyError,
    Message,
    Role,
    StreamableParser,
)

from burrito.plugins import BasePlugin, ErrorPlugin
from burrito.plugins.chat import (
    ContextManagerPluginChat,
    ReasoningTextPluginChat,
    OutputTextPluginChat,
    ToolPluginChat,
)
from burrito.plugins.responses import (
    ContextManagerPluginResponses,
    ReasoningTextPluginResponses,
    OutputTextPluginResponses,
    ToolPluginResponses,
)

from burrito.services.harmony import (
    ENCODING,
    build_conversation,
    build_user_message,
    render_conversation_for_completion,
)
from burrito.common.config import settings
from burrito.common.utils import unix_timestamp_in_ms
from burrito.types.adapter import (
    AdapterCompletionToken,
    AdapterConversationInputs,
    AdapterConversationState,
    AdapterCreateParamsChat,
    AdapterCreateParamsResponses,
)

from .token_handler import (
    normalize_completion_token,
)
from .tool_handler import ToolHandler
from .transition_handler import TransitionHandler


class AdapterStateHandler:
    def __init__(
        self,
        manager: AdapterConversationHandler,
        stream_to_caller: bool,
        log_id: str,
    ):
        self.manager = manager
        self.stream_to_caller = stream_to_caller

        self.conversation: Conversation
        self.conversation_inputs: AdapterConversationInputs
        self.prompt_tokens: List[int]
        self.parser: StreamableParser

        self.events: List[Dict[str, Any]] = []
        self.completions: List[Completion] = []
        self.response_tokens: List[AdapterCompletionToken] = []
        self.reasoning_tokens: List[AdapterCompletionToken] = []
        self.response_buffer: str = ""

        self.log_id = log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"ash_{self.log_id}"}

        self.parser_channel: Optional[str] = None
        self.parser_state = AdapterConversationState.INITIAL
        self.sequence_number = 0
        self.output_index = -1
        self.created_event_fired: bool = False
        self.is_done: bool = False

        self.output_object: Union[
            Response,
            List[Union[AdapterChatCompletionChunk, AdapterChatCompletion]],
        ]

        self.plugins: List[BasePlugin]
        self._active_plugins_by_state: dict[str, list[BasePlugin]] = {}
        self.error_plugin = ErrorPlugin(self)

        self.created_at = unix_timestamp_in_ms()
        self.recover_state_attempts = 0
        self.recovery_message: Optional[Message] = None
        self.extra_messages: List[Message] = []
        self._init_conversation()
        self._init_plugins()

        self.tool_handler = ToolHandler(self)
        self.transition_handler = TransitionHandler(self)

    def _init_plugins(self):
        match self.manager.params:
            case AdapterCreateParamsChat():
                self.plugins = [
                    ContextManagerPluginChat(self),
                    ReasoningTextPluginChat(self),
                    OutputTextPluginChat(self),
                    ToolPluginChat(self),
                    # TODO: continue, output, tool and then summaries, maybe
                ]
            case AdapterCreateParamsResponses():
                self.plugins = [
                    ContextManagerPluginResponses(self),
                    ReasoningTextPluginResponses(self),
                    OutputTextPluginResponses(self),
                    ToolPluginResponses(self),
                ]
            case _:
                pass  # TODO: maybe anthropic messages?
        for plugin in self.plugins:
            for state in plugin.subscribed_states:
                self._active_plugins_by_state.setdefault(state, []).append(plugin)

    async def _fire_created_event(self):
        if self.created_event_fired:
            return
        self.created_event_fired = True

    def _init_conversation(self, extra_messages: Optional[List[Message]] = None):
        params = self.manager.params
        python_tool = self.manager.python_tool
        browser_tool = self.manager.browser_tool
        conversation, inputs = build_conversation(
            params, extra_messages, python_tool, browser_tool
        )
        self.conversation = conversation
        self.conversation_inputs = inputs
        self.prompt_tokens = render_conversation_for_completion(self.conversation)
        self.parser = StreamableParser(ENCODING, Role.ASSISTANT)

    async def _push_event(self, event: bytes):
        await self.manager.output_queue.put(event)
        self.sequence_number += 1

    async def push_event(self, event: bytes):
        await self._push_event(event)

    # TODO: figure this out, only responses supports streamed errors?
    async def push_error(self, message: str, code: str):
        """Record an error and transition the state machine to *ERROR*.

        The caller traditionally pushes errors directly from the conversation
        handler (e.g. to signal a backend timeout or JSON decode failure).  The
        state machine itself is agnostic to error details, but pushing an
        error should:

        1.  Transition the machine into :data:`~ProxyConversationState.ERROR`.
        2.  Emit a structured SSE payload when running in streaming mode.
        3.  Safely stop further token processing by marking the stream as
            finished.
        """

        # Switch to the dedicated error state so that no further normal
        # transitions are processed and plugins can hook into the error event.
        self.parser_state = AdapterConversationState.ERROR
        # Mark the state machine as finished to unblock the consumer loop.
        self.is_done = True
        # Notify the ConversationHandler that the stream should finish.
        # This ensures the consumer loop in ``generate_streamed`` exits.
        if hasattr(self.manager, "is_finished"):
            self.manager.is_finished.set()

        payload = {
            "type": "error",
            "code": code,
            "message": message,
            "param": None,
            "sequence_number": self.sequence_number,
        }
        # Emit the error to the caller.  The BasePlugin implementation will
        # decide if the payload should be streamed (SSE) or ignored (chat).
        await self.error_plugin.on_error(payload)

    def _add_recovery_message(self, text: str):
        message = build_user_message(text, "HARNESS-SENTINEL-v1")
        bfr = f"\n\n🚨🚨🚨\n\n{message.content[0].text}\n\n🚨🚨🚨\n\n" # type: ignore
        self.response_buffer += bfr
        self.recovery_message = message

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
        # TODO: decide, allow assistant to continue or kill stream and bubble up
        if self.recover_state_attempts >= settings.MAX_RECOVER_STATE_ATTEMPTS:
            raise RecursionError("Reached maximum state recover attempts.")

        self.manager._stop_stream()
        prev_messages = self.parser.messages
        if self.recovery_message:
            prev_messages.append(self.recovery_message)
            self.recovery_message = None

        for i in prev_messages:
            self.extra_messages.append(i)
        self._init_conversation(extra_messages=self.extra_messages)
        self.manager._init_stream()
        self.recover_state_attempts += 1

    def _count_reasoning_tokens(self, token: AdapterCompletionToken):
        if self.parser_state in (
            AdapterConversationState.INITIAL,
            AdapterConversationState.CREATED,
            AdapterConversationState.IN_PROGRESS,
            AdapterConversationState.REASONING,
            AdapterConversationState.TOOL_INPUT,
        ):
            self.reasoning_tokens.append(token)
        else:
            return

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

        # TODO: investigate, weird special case where assistant emitting same
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
            # TODO: does this still happen? add recovery message to assistant?
            return

        self.completions.append(completion)
        self.response_tokens.append(token)
        self.response_buffer
        try:
            self.parser.process(token.id)
        except HarmonyError as e:
            self.logger.warning(f"_process_completion: {repr(e)}", extra=self.log_extra)
            # no recovery message since it can be a variety of reasons,
            # - HarmonyError('unexpected tokens remaining in message header: List[str]') (rare, mostly cahght by validations)
            # - HarmonyError('Unknown role: assistant<|channel|>commentary')
            # - anything else?
            self._add_recovery_message(
                f"**Invalid output**: bad token sequence:\n{repr(e.args[0])}"
            )
            return self._recover_state()

        self._count_reasoning_tokens(token)
        self.response_buffer += token.text
        await self.transition_handler.transition(token)
        await self.tool_handler.maybe_call_native_tool()
        await self._fire_created_event()

    def _log_stats(self):
        n_tokens_prompt = len(self.prompt_tokens)
        n_tokens_response = len(self.response_tokens)
        n_tokens_total = n_tokens_prompt + n_tokens_response

        first_token = self.response_tokens[0]
        last_token = self.response_tokens[-1]

        delta_pp = first_token.created_at - self.created_at
        delta_tg = last_token.created_at - first_token.created_at
        delta_total = (delta_pp + delta_tg) / 1000

        tps_pp = n_tokens_prompt / (delta_pp / 1000)
        tps_tg = n_tokens_response / (delta_tg / 1000)

        self.logger.info(
            (
                f"{'prompt:':<12}"
                f"{delta_pp / 1000:>10,.2f}s"
                f"{n_tokens_prompt:>10,} tokens"
                f"{delta_pp / n_tokens_prompt:>10,.2f} ms/tok"
                f"{tps_pp:>10,.0f} tok/s"
            ),
            extra=self.log_extra,
        )
        self.logger.info(
            (
                f"{'eval: ':<12}"
                f"{delta_tg / 1000:>10,.2f}s"
                f"{n_tokens_response:>10,} tokens"
                f"{delta_tg / n_tokens_response:>10,.2f} ms/tok"
                f"{tps_tg:>10,.0f} tok/s"
            ),
            extra=self.log_extra,
        )

        self.logger.info(
            (f"{'total:':<12}{delta_total:>10,.2f}s{n_tokens_total:>10,} tokens"),
            extra=self.log_extra,
        )

    def _cleanup_on_done(self, completion: Union[Completion, str]):
        self.is_done = isinstance(completion, str) and completion == "[DONE]"
        if not self.is_done:
            return
        self._log_stats()
        self.response_buffer

    async def process_completion(self, completion: Union[Completion, str]):
        await self._process_completion(completion)
        self._cleanup_on_done(completion)
