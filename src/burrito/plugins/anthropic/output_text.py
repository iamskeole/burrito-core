from typing import Set, Any, Dict

from anthropic.types.message import Message
from anthropic.types.content_block_start_event import ContentBlockStartEvent
from anthropic.types.content_block_delta_event import ContentBlockDeltaEvent
from anthropic.types.content_block_stop_event import ContentBlockStopEvent
from anthropic.types.text_block import TextBlock
from anthropic.types.text_delta import TextDelta
from anthropic.types.citations_web_search_result_location import (
    CitationsWebSearchResultLocation,
)
from anthropic.types.citations_delta import CitationsDelta

from burrito.plugins.anthropic.base_plugin import BasePluginAnthropic
from burrito.types.adapter import AdapterConversationState
from burrito.handlers.token_handler import AdapterCompletionToken


class OutputTextPluginAnthropic(BasePluginAnthropic):
    def __init__(self, manager):
        super().__init__(manager)
        self.has_partial_citations = False
        self.annotations: list[Dict[str, Any]] = []
        self.citations: list[CitationsWebSearchResultLocation] = []
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
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )
        self.manager.output_index += 1
        content_block = TextBlock(type="text", citations=[], text="")
        event = ContentBlockStartEvent(
            type="content_block_start",
            content_block=content_block,
            index=self.manager.output_index,
        )
        self.manager.output_object.content.append(content_block)
        await self.put_event(event)

    async def handle_on_exit_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )
        event = ContentBlockStopEvent(
            type="content_block_stop", index=self.manager.output_index
        )
        await self.put_event(event)

    async def handle_browser_annotations(self):
        if not self.manager.manager.browser_tool_used:
            return
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.content[self.manager.output_index]
        assert isinstance(output_item, TextBlock), (
            f"Expected a ResponseOutputMessage, but got {type(output_item)}"
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
            if url in self.current_citations:
                return

            citation = CitationsWebSearchResultLocation(
                type="web_search_result_location",
                cited_text=a["cited_text"],
                encrypted_index="",
                url=a["url"],
                title=a["title"],
            )
            delta = CitationsDelta(citation=citation, type="citations_delta")
            await self.put_event(
                ContentBlockDeltaEvent(
                    type="content_block_delta",
                    delta=delta,
                    index=self.manager.output_index,
                )
            )
            self.current_citations.append(url)
            self.annotations.append(a)
            self.citations.append(citation)

    async def handle_on_token(self, token: AdapterCompletionToken):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Message), (
            f"Expected a Message, but got {type(output_object)}"
        )

        self.output_delta_buffer += token.text
        self.debug_full_buffer += token.text

        await self.handle_browser_annotations()
        if self.has_partial_citations:
            return

        delta = TextDelta(type="text_delta", text=self.output_delta_buffer)
        event = ContentBlockDeltaEvent(
            type="content_block_delta", delta=delta, index=self.manager.output_index
        )
        output_index = self.manager.output_index
        content_item = self.manager.output_object.content[output_index]
        assert isinstance(content_item, TextBlock), (
            f"Expected a TextBlock, but got {type(content_item)}"
        )
        content_item.text += self.output_delta_buffer
        content_item.citations = self.citations  # type: ignore
        await self.put_event(event)

        self.current_output_text_content += self.output_delta_buffer
        self.output_delta_buffer = ""

    async def on_enter_state(self, state: AdapterConversationState):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: AdapterConversationState):
        await self.handle_on_exit_state()

    async def on_token(self, token: AdapterCompletionToken):
        await self.handle_on_token(token)
