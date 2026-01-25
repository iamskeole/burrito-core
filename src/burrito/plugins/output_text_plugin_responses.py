from __future__ import annotations

from typing import TYPE_CHECKING, Set, Any

from openai.types.responses.response import Response

if TYPE_CHECKING:
    from burrito.handlers.state_handler import (
        AdapterStateHandler,
    )
    from burrito.handlers.token_handler import (
        AdapterCompletionToken,
    )


from openai.types.responses.response_content_part_done_event import (
    ResponseContentPartDoneEvent,
)
from openai.types.responses.response_output_item_added_event import (
    ResponseOutputItemAddedEvent,
)
from openai.types.responses.response_output_item_done_event import (
    ResponseOutputItemDoneEvent,
)
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_text import (
    ResponseOutputText,
    AnnotationURLCitation,
    Annotation,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent
from openai.types.responses.response_output_text_annotation_added_event import (
    ResponseOutputTextAnnotationAddedEvent,
)

from burrito.plugins.base_plugin_responses import BasePluginResponses
from burrito.common.utils import random_uuid


class OutputTextPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.content_index = 0

        self.has_partial_citations = False
        self.annotations: list[dict[str, Any]] = []
        self.current_annotations = []
        self.current_output_text_content = ""
        self.output_delta_buffer = ""
        self.debug_full_buffer = ""
        self.citation_index = 1
        self.cited_urls = []

    @property
    def subscribed_states(self) -> Set[str]:
        return {"output_text"}

    # TODO: handle content_part_added event
    async def handle_on_enter_state(self):
        self.manager.output_index += 1
        output_item = ResponseOutputMessage(
            id=f"msg_{random_uuid()}",
            content=[ResponseOutputText(annotations=[], text="", type="output_text")],
            role="assistant",
            status="in_progress",
            type="message",
        )
        event = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            type="response.output_item.added",
            sequence_number=self.manager.sequence_number,
        )
        await self.push_event(event, output_item)

    async def handle_browser_annotations(self):
        if not self.manager.manager.browser_tool_used:
            return
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]
        assert isinstance(output_item, ResponseOutputMessage), (
            f"Expected a ResponseOutputMessage, but got {type(output_item)}"
        )

        browser_tool = self.manager.manager.browser_tool

        # we normalize on the full current text to get the right indices in citations
        updated_output_text, annotations, has_partial_citations = (
            browser_tool.normalize_citations(
                old_content=self.current_output_text_content + self.output_delta_buffer,
                current_citations=self.annotations
            )
        )

        self.has_partial_citations = has_partial_citations

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
            if url not in self.cited_urls:
                self.cited_urls.append(url)
            self.annotations.append(a)
            citation = AnnotationURLCitation(**a)
            event = ResponseOutputTextAnnotationAddedEvent(
                type="response.output_text.annotation.added",
                output_index=self.manager.output_index,
                content_index=self.content_index,
                sequence_number=self.manager.sequence_number,
                item_id=output_item.id,
                annotation_index=len(self.annotations),
                annotation=citation,
            )
            await self.push_event(event)
            self.content_index += 1

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]
        assert isinstance(output_item, ResponseOutputMessage), (
            f"Expected a ResponseOutputMessage, but got {type(output_item)}"
        )

        self.output_delta_buffer += token.text
        self.debug_full_buffer += token.text

        await self.handle_browser_annotations()
        if self.has_partial_citations:
            return

        delta = ResponseOutputText(
            annotations=[AnnotationURLCitation(**a) for a in self.annotations],
            text=self.output_delta_buffer,
            type="output_text",
            logprobs=None,
        )
        event = ResponseTextDeltaEvent(
            content_index=self.content_index,
            delta=self.output_delta_buffer,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_text.delta",
            logprobs=[],
        )

        output_item.content.append(delta)
        await self.push_event(event)
        self.content_index += 1

        self.current_output_text_content += self.output_delta_buffer
        self.output_delta_buffer = ""

    async def handle_on_exit_state(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]

        assert isinstance(output_item, ResponseOutputMessage), (
            f"Expected a ResponseOutputText, but got {type(output_item)}"
        )
        assert isinstance(output_item.content, list), (
            f"Expected list[Content], but got {type(output_item.content)}"
        )
        assert all([isinstance(i, ResponseOutputText) for i in output_item.content]), (
            f"Expected ResponseOutputText but got {[type(i) for i in output_item.content]}"
        )

        text = "".join([i.text for i in output_item.content])  # type: ignore (handled above in assert)
        delta = ResponseOutputText(
            annotations=[], text=text, type="output_text", logprobs=None
        )
        output_item.content = [delta]

        event_text_done = ResponseTextDoneEvent(
            content_index=self.content_index,
            item_id=output_item.id,
            logprobs=[],
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            text=text,
            type="response.output_text.done",
        )
        event_content_part_done = ResponseContentPartDoneEvent(
            content_index=self.content_index,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            part=delta,
            sequence_number=self.manager.sequence_number,
            type="response.content_part.done",
        )
        event_output_item_done = ResponseOutputItemDoneEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.done",
        )

        await self.push_event(event_text_done)
        await self.push_event(event_content_part_done)
        await self.push_event(event_output_item_done)

        self.manager.manager.browser_tool_used = False
        self.annotations = []
        self.current_output_text_content = ""
        self.output_delta_buffer = ""
        self.debug_full_buffer = ""
        self.citation_index = 1
        self.cited_urls = []

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
