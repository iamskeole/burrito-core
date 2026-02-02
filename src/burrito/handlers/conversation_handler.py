import asyncio
from typing import AsyncGenerator, Dict, List, Union

import async_timeout
from fastapi import Request
from openai.types.completion import Completion
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.responses import Response

from gpt_oss.tools.python_docker.docker_tool import PythonTool

from burrito.tools.browser.tool import BurritoBrowser

from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid, unix_timestamp_in_ms
from burrito.types.adapter import AdapterCreateParams
from burrito.types.adapter.adapter_chat_completion_chunk import AdapterChatCompletionChunk

from .state_handler import AdapterStateHandler


class AdapterConversationHandler:
    def __init__(
        self,
        request: Request,
        params: AdapterCreateParams,
        generator: AdapterGenerationHandler,
        python_tool: PythonTool,
        browser_tool: BurritoBrowser,
        forwarded_headers: Dict[str, str] = {},
    ):
        self.request = request
        self.params = params
        self.created_at = unix_timestamp_in_ms()
        self.stream_to_caller = params.stream or False

        self.output_queue = asyncio.Queue()
        self.is_finished = asyncio.Event()

        self.generator = generator
        self.stream: AsyncGenerator[Union[Completion, Dict, str], None]
        self.prompt_tokens: List[int]
        self.state_handler: AdapterStateHandler
        self.python_tool = python_tool
        self.browser_tool = browser_tool
        self.browser_tool_used = False
        self.forwarded_headers = forwarded_headers

        self.log_id = random_uuid()
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"ach_{self.log_id}"}

        self._init_state_handler()
        self._init_stream()

    def _init_state_handler(self):
        self.state_handler = AdapterStateHandler(
            manager=self,
            stream_to_caller=self.stream_to_caller,
            log_id=self.log_id,
        )

    def _init_stream(self):
        self.generator.log_id = self.log_id
        self.generator.can_stream = True
        prompt_token_ids = self.state_handler.prompt_tokens
        params = self.params
        self.stream = self.generator.generate(
            prompt_token_ids, params, self.forwarded_headers
        )

    def _stop_stream(self):
        self.generator.can_stream = False

    async def _stream_completions(self):
        sm = self.state_handler
        try:
            while 1:
                # detect client disconnects
                # TODO: handle generation stop, when client stops manually
                if await self.request.is_disconnected():
                    self._stop_stream()
                    msg = "Client disconnected, stopping generation."
                    self.logger.info(msg, extra=self.log_extra)
                    break

                # handle backend stalls
                try:
                    async with async_timeout.timeout(
                        settings.BACKEND_INTER_TOKEN_TIMEOUT
                    ):
                        completion = await anext(self.stream)
                except StopAsyncIteration:
                    # break  # stream finished successfully
                    # we pass instead of breaking, so we keep the main loop to
                    # the caller still open if the model goes haywire and we
                    # need to recover from that
                    pass
                except asyncio.TimeoutError:
                    # TODO: increase timeout, prompt processing may kill this when cache misses
                    msg = "Backend timed out between tokens"
                    self.logger.error(msg, extra=self.log_extra)
                    await sm.push_error(msg, "ERR_BACKEND_TIMEOUT")
                    break  # TODO here, again, figure out if we retry to save to db

                if isinstance(completion, dict):
                    msg = f"Backend error: {completion.get('error')}"
                    self.logger.error(msg, extra=self.log_extra)
                    await sm.push_error(msg, "ERR_BACKEND_EXCEPTION")
                    break

                await sm.process_completion(completion)
                if sm.is_done:
                    self.is_finished.set()
                    break

        except Exception as e:
            msg = f"Exception in stream processor:\n{repr(e)}"
            self.logger.exception(msg, extra=self.log_extra)
            await sm.push_error(msg, "ERR_STREAM_PROCESSOR")
        finally:
            self.is_finished.set()
            # Ensure the backend generator stream is closed if possible.
            try:
                await self.stream.aclose()
            except Exception:
                # Some generators may not support `aclose`.  Silently ignore.
                pass
            
            # sentinel to wake up the consumer
            self.output_queue.put_nowait(None)

    async def return_stream(self) -> AsyncGenerator[bytes, None]:
        # use TaskGroup for safe concurrency
        sm = self.state_handler
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._stream_completions())

                # consumer loop
                while True:
                    item = await self.output_queue.get()
                    if item is None:
                        break
                    yield item
        except Exception as e:
            # if something in the TaskGroup (eg cancelation due to an error)
            # throws, we want to surface that as an error event and stop the
            # generator
            msg = f"TaskGroup caught an unhandled exception:\n{repr(e)}"
            self.logger.error(msg, extra=self.log_extra)
            await sm.push_error(msg, "ERR_TASK_GROUP_EXCEPTION")

    def _return_json_responses(self):
        output_object = self.state_handler.output_object
        assert isinstance(output_object, Response), (
            f"Expected list, got {type(output_object)}"
        )
        return output_object.model_dump()

    def _return_json_chat(self):
        output_object = self.state_handler.output_object
        assert isinstance(output_object, list), (
            f"Expected list, got {type(output_object)}"
        )

        if type(output_object[0]) is not AdapterChatCompletionChunk:
            return {
                "error": f"Expected AdapterChatCompletionChunk, got {type(output_object[0])}"
            }

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

        raise NotImplementedError(f"Unsupported output object: {type(output_object)}")
