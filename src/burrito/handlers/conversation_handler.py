import asyncio
from typing import AsyncGenerator, Dict, List, Union

import async_timeout
from fastapi import Request
from openai.types.completion import Completion

from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.sandbox_handler import SandboxHandler
from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid, unix_timestamp_in_ms
from burrito.types.adapter import AdapterCreateParams

from .state_handler import AdapterStateHandler


class AdapterConversationHandler:
    def __init__(
        self,
        request: Request,
        params: AdapterCreateParams,
        generator: AdapterGenerationHandler,
        sandbox_handler: SandboxHandler,
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
        self.sandbox_handler = sandbox_handler

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
        self.stream = self.generator.generate(prompt_token_ids, params)

    def _stop_stream(self):
        self.generator.can_stream = False

    async def _stream_completions(self):
        try:
            sm = self.state_handler
            while 1:
                completion = "streaming"
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
            await self.state_handler.push_error(msg, "ERR_STREAM_PROCESSOR")
        finally:
            self.is_finished.set()
            # Ensure the backend generator stream is closed if possible.
            try:
                await self.stream.aclose()
            except Exception:
                # Some generators may not support `aclose`.  Silently ignore.
                pass

    async def return_stream(self) -> AsyncGenerator[bytes, None]:
        # use TaskGroup for safe concurrency
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._stream_completions())

                # consumer loop
                while (
                    not self.is_finished.is_set()
                    or not self.output_queue.empty()
                    or not self.state_handler.is_done
                ):
                    try:
                        # TODO: figure out optimal timeout here
                        item = await asyncio.wait_for(
                            self.output_queue.get(), timeout=1.0
                        )
                        yield item
                    except asyncio.TimeoutError:
                        if (
                            all(t.done() for t in tg._tasks)
                            and self.output_queue.empty()
                        ):
                            break
                        continue
        except Exception as e:
            # if something in the TaskGroup (eg cancelation due to an error)
            # throws, we want to surface that as an error event and stop the
            # generator
            msg = f"TaskGroup caught an unhandled exception:\n{repr(e)}"
            self.logger.error(msg, extra=self.log_extra)
            await self.state_handler.push_error(msg, "ERR_TASK_GROUP_EXCEPTION")

    async def return_json(self) -> Dict:
        # This consumes the entire stream but doesn't yield anything to the caller.
        # It just runs the process to populate the internal state.
        async for _ in self.return_stream():
            pass  # Consume the stream to completion

        # After the stream is done, get the final result.
        if self.state_handler.is_done:
            return self.state_handler.output_object.model_dump()
            return {"done": "ok"}  # TODO: self.state_handler.json_output()
        else:
            # Handle cases where generation failed
            return {"error": "Generation did not complete successfully."}
