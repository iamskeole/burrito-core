from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.adapter.handlers.token_handler import (
        AdapterCompletionToken,
    )
from .base_plugin import BasePlugin


class ReasoningSummaryPluginResponses(BasePlugin):
    def __init__(self, manager):
        super().__init__(manager)
        self._reasoning_queue: asyncio.Queue | None = None
        self._summarizer_task: asyncio.Task | None = None

    @property
    def subscribed_states(self) -> Set[str]:
        return {"todo"}
        # return {"reasoning.start", "reasoning.delta", "reasoning.end"}

    async def on_enter_state(self, state: str):
        self.logger.info(
            "Entering reasoning state. Starting summarizer.", extra=self.log_extra
        )
        await self.manager._push_event("thinking_started")
        self._reasoning_queue = asyncio.Queue()
        self._summarizer_task = asyncio.create_task(self._summarize_reasoning_stream())

    async def on_exit_state(self, state: str):
        self.logger.info(
            "Exiting reasoning state. Stopping summarizer.", extra=self.log_extra
        )
        if self._reasoning_queue:
            await self._reasoning_queue.put(None)
        if self._summarizer_task:
            await self._summarizer_task
        self._summarizer_task = None
        self._reasoning_queue = None
        await self.manager._push_event("thinking_completed")

    async def on_token(self, token: AdapterCompletionToken, state: str):
        if self._reasoning_queue:
            await self._reasoning_queue.put(token)

    async def close(self):
        if self._summarizer_task and not self._summarizer_task.done():
            self.logger.warning("Force-closing summarizer task.", extra=self.log_extra)
            self._summarizer_task.cancel()
            try:
                await self._summarizer_task
            except asyncio.CancelledError:
                pass

    async def _summarize_reasoning_stream(self):
        self.logger.info("Summarizer task started.", extra=self.log_extra)
        reasoning_buffer = ""
        SUMMARY_PROMPT_TEMPLATE = (
            "Briefly summarize the following internal monologue from an AI: {text}"
        )

        async def perform_summary(text_to_summarize: str):
            if not text_to_summarize.strip():
                return
            self.logger.info(
                f"Summarizing buffer of {len(text_to_summarize)} chars.",
                extra=self.log_extra,
            )
            prompt_text = SUMMARY_PROMPT_TEMPLATE.format(text=text_to_summarize)
            prompt_token_ids = ENCODING.encode(prompt_text)
            summary_generator = self.manager.backend_client.generate(
                prompt_token_ids, [], []
            )
            async for summary_chunk in summary_generator:
                if isinstance(summary_chunk, dict):
                    continue
                summary_token = self.manager._normalize_chunk(summary_chunk)
                if summary_token:
                    await self.manager._push_event(
                        "summary_delta", summary_text=summary_token.text
                    )

        try:
            while True:
                token_info = await self._reasoning_queue.get()
                if token_info is None:
                    break

                reasoning_buffer += token_info.text
                self._reasoning_queue.task_done()

                if reasoning_buffer.count("\n") >= 3:
                    await perform_summary(reasoning_buffer)
                    reasoning_buffer = ""

            await perform_summary(reasoning_buffer)  # Final summary
        except asyncio.CancelledError:
            self.logger.info("Summarizer task was cancelled.", extra=self.log_extra)
        except Exception:
            self.logger.exception(
                "Summarizer task failed catastrophically.", extra=self.log_extra
            )
        finally:
            self.logger.info("Summarizer task finished.", extra=self.log_extra)
