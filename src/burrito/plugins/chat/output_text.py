from __future__ import annotations

from typing import TYPE_CHECKING, Set, Any, List

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler
    from burrito.handlers.token_handler import AdapterCompletionToken


from openai.types.chat.chat_completion_chunk import ChatCompletionChunk


from burrito.types.adapter.adapter_chat_completion_chunk import (
    AdapterChatCompletionChunkChoice,
    AdapterChatCompletionChunkChoiceDelta,
)
from burrito.types.adapter import AdapterConversationState
from burrito.plugins.chat.base_plugin import BasePluginChat


class OutputTextPluginChat(BasePluginChat):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager

        self.has_partial_citations = False
        self.annotations: list[dict[str, Any]] = []
        self.current_annotations = []
        self.current_output_text_content = ""
        self.output_delta_buffer = ""
        self.debug_full_buffer = ""
        self.current_citation_index = 0
        self.current_citations = []

    @property
    def subscribed_states(self) -> Set[str]:
        return {AdapterConversationState.OUTPUT_TEXT}

    async def handle_on_enter_state(self):
        pass  # no enter event for chat/completions

    async def handle_browser_annotations(self):
        if not self.manager.manager.browser_tool_used:
            return
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        browser_tool = self.manager.tool_handler.browser_tool
        if browser_tool is None:
            return

        # we normalize on the full current text to get the right indices in citations
        (
            updated_output_text,
            annotations,
            has_partial_citations,
            current_citation_index,
        ) = browser_tool.normalize_citations(
            old_content=self.current_output_text_content + self.output_delta_buffer,
            current_citations=self.annotations,
            current_citation_index=self.current_citation_index,
        )

        self.has_partial_citations = has_partial_citations
        self.current_citation_index = current_citation_index

        # remove the current text to get back the delta but now normalized
        self.output_delta_buffer = updated_output_text[
            len(self.current_output_text_content) :
        ]
        # Filter annotations to only include those whose start_index is not already present in current_annotations
        # this is to avoid sending duplicate annotations as multiple annotations can't be in the same place
        existing_start_indices = {a["start_index"] for a in self.annotations}
        new_annotations = [
            a for a in annotations if a["start_index"] not in existing_start_indices
        ]
        for a in new_annotations:
            url = a["url"]
            if url not in self.current_citations:
                self.current_citations.append(url)
            self.annotations.append(a)

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], ChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )

        self.output_delta_buffer += token.text
        self.debug_full_buffer += token.text

        await self.handle_browser_annotations()
        if self.has_partial_citations:
            return

        choice = AdapterChatCompletionChunkChoice(
            index=0,
            delta=AdapterChatCompletionChunkChoiceDelta(
                role="assistant",
                content=self.output_delta_buffer,
            ),
        )
        chunk = self.build_chunk_object(choice)
        self.manager.output_object.append(chunk)
        await self.put_event(chunk)

        self.current_output_text_content += self.output_delta_buffer
        self.output_delta_buffer = ""

    async def handle_on_exit_state(self):
        pass  # no exit event for chat/completions

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
