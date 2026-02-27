import asyncio
import logging
from typing import AsyncGenerator, Dict, List, Optional, Union

import async_timeout
from anthropic.types.message import Message as AnthropicMessage
from fastapi import Request
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.completion import Completion
from openai.types.responses import Response

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import unix_timestamp_in_ms, wire_api_label_from_params
from burrito.handlers.generation_handler import GenerationHandler
from burrito.handlers.session_handler import SessionHandler
from burrito.handlers.state_handler import StateHandler
from burrito.routes.metrics import generation_requests_total
from burrito.types.conversation_error import ConversationError
from burrito.types.wire_api_params import WireApiParams


class ConversationHandler:
    def __init__(
        self,
        request: Request,
        params: WireApiParams,
        generator: GenerationHandler,
        session_handler: SessionHandler,
        forwarded_headers: Dict[str, str] = {},
    ):
        self.request = request
        self.params = params
        self.created_at = unix_timestamp_in_ms()
        self.stream_to_caller = params.stream or False

        self.output_queue = asyncio.Queue()
        self.is_finished = asyncio.Event()

        self.session_handler = session_handler
        self.generator = generator
        self.stream: AsyncGenerator[Union[Completion, Dict, str], None]
        self.prompt_tokens: List[int]
        self.state_handler: StateHandler
        self.browser_tool_used = False
        self.forwarded_headers = forwarded_headers

        self.log_id: str = ""
        self.logger: logging.Logger
        self.log_extra: Dict[str, str]

        self._is_stopped = False

        self._init_state_handler()
        self._init_logger()
        self._init_stream()

    def _init_logger(self):
        self.log_id = self.state_handler.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": self.log_id}

    def _init_state_handler(self):
        self.state_handler = StateHandler(
            manager=self, stream_to_caller=self.stream_to_caller
        )

        # increment generation requests counter
        m = self.params.model
        w = wire_api_label_from_params(self.params)
        generation_requests_total.labels(wire_api=w, model=m).inc()

    def _init_stream(self):
        self._is_stopped = False
        self.generator.can_stream = True
        self.generator.log_id = self.log_id
        self.stream = self.generator.generate(
            prompt_token_ids=self.state_handler.prompt_tokens,
            params=self.params,
            headers=self.forwarded_headers,
        )

    def _stop_stream(self, msg: Optional[str] = None):
        if self._is_stopped:
            return
        self._is_stopped = True
        self.generator.can_stream = False
        if msg is None:
            return
        if not settings.DEBUG_CLIENT_DISCONNECTS:
            return
        self.logger.debug(msg, extra=self.log_extra)

    async def _watch_disconnect(self):
        try:
            while True:
                message = await self.request.receive()
                if message.get("type") == "http.disconnect":
                    self._stop_stream("Client disconnected inside _watch_disconnect.")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._stop_stream(f"_watch_disconnect exited with error: {e}")

    async def _stream_completions(self):
        sm = self.state_handler
        timeout = settings.BACKEND_INTER_TOKEN_TIMEOUT
        try:
            while 1:
                completion = None

                try:
                    async with async_timeout.timeout(timeout):
                        completion = await anext(self.stream)

                # handle backend stalls
                except asyncio.TimeoutError:
                    msg = "Backend timed out between tokens"
                    self.logger.error(msg, extra=self.log_extra)
                    await sm.put_error(msg, "ERR_BACKEND_TIMEOUT")
                    break
                # stream finished successfully; pass instead of break
                # to keep connection to caller alive in case the model
                # goes haywire and we need to _recover_state() from that
                except StopAsyncIteration:
                    # pass
                    break

                if completion is None:
                    break

                await sm.process_completion(completion)
                if sm.is_done:
                    self.is_finished.set()
                    break

        except Exception as e:
            msg = f"Exception in stream processor:\n{repr(e)}"
            self.logger.exception(msg, extra=self.log_extra)
            await sm.put_error(msg, "ERR_STREAM_PROCESSOR")
        finally:
            self.is_finished.set()
            # best efforts ensure the backend generator stream is closed
            try:
                await self.stream.aclose()
            except Exception:
                # some generators may not support aclose, we silently ignore
                pass

            # sentinel to wake up the consumer
            self.output_queue.put_nowait(None)

    async def return_stream(self) -> AsyncGenerator[bytes, None]:
        sm = self.state_handler
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._stream_completions())

                watch_task = None
                if not self.stream_to_caller:
                    watch_task = tg.create_task(self._watch_disconnect())

                while True:
                    item = await self.output_queue.get()
                    if item is None:
                        break
                    yield item

                if watch_task:
                    watch_task.cancel()

        except asyncio.CancelledError:
            # this triggers automatically when a STREAMED client disconnects
            self._stop_stream("Client disconnected outside _watch_disconnect.")
            raise  # re-raise the cancellation so fastapi cleans up

        except Exception as e:
            msg = f"TaskGroup caught an unhandled exception:\n{repr(e)}"
            self.logger.error(msg, extra=self.log_extra)
            await sm.put_error(msg, "ERR_TASK_GROUP_EXCEPTION")

    async def return_json(self) -> Dict:
        async for _ in self.return_stream():
            pass

        assert self.state_handler.is_done, "Generation did not complete successfully."

        output_object = self.state_handler.output_object

        if isinstance(output_object, Response):
            return output_object.model_dump()

        if isinstance(output_object, list) and isinstance(
            output_object[-1], ChatCompletion
        ):
            out = output_object[-1].model_dump()
            return out

        if isinstance(output_object, AnthropicMessage):
            return output_object.model_dump()

        if isinstance(output_object, ConversationError):
            return output_object.model_dump()

        raise NotImplementedError(f"Unsupported output object: {type(output_object)}")
