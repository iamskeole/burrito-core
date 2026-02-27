from __future__ import annotations

from typing import TYPE_CHECKING, Any, Set

from openai.types.responses.response import Response
from openai.types.responses.response_content_part_added_event import (
    ResponseContentPartAddedEvent,
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
    AnnotationURLCitation,
    ResponseOutputText,
)
from openai.types.responses.response_output_text_annotation_added_event import (
    ResponseOutputTextAnnotationAddedEvent,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent

from burrito.common.utils import random_uuid
from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.types.conversation_enums import ConversationState

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler
    from burrito.handlers.token_handler import ConversationToken


class OutputTextPluginResponses(BasePluginResponses):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager
        # hardcoded, not incremented, to match gpt-oss reference implementation
        # only one content item, which means somehow multiple are allowed in .content=[]?
        self.content_index = 0

        self.has_partial_citations = False
        self.annotations: list[dict[str, Any]] = []
        self.current_annotations = []
        self.current_output_text_content = ""
        self.output_delta_buffer = ""
        self.debug_full_buffer = ""
        self.current_citations = []

    @property
    def subscribed_states(self) -> Set[str]:
        return {ConversationState.OUTPUT_TEXT}

    async def handle_on_enter_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(output_object)}"
        )
        self.manager.output_index += 1
        output_item = ResponseOutputMessage(
            id=f"msg_{random_uuid()}",
            content=[],
            role="assistant",
            status="in_progress",
            type="message",
        )
        event_item = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            type="response.output_item.added",
            sequence_number=self.manager.sequence_number,
        )
        self.manager.output_object.output.append(output_item)
        await self.put_event(event_item)

        event_content = ResponseContentPartAddedEvent(
            type="response.content_part.added",
            content_index=self.content_index,
            output_index=self.manager.output_index,
            item_id=output_item.id,
            sequence_number=self.manager.sequence_number,
            part=ResponseOutputText(
                annotations=self.current_annotations,
                text=self.output_delta_buffer,
                type="output_text",
            ),
        )
        await self.put_event(event_content)

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

        browser_tool = self.manager.tool_handler.browser_tool
        if browser_tool is None:
            return

        # we normalize on the full current text to get the right indices in citations
        (updated_output_text, annotations, has_partial_citations) = (
            browser_tool.normalize_citations(
                old_content=self.current_output_text_content + self.output_delta_buffer,
                current_citations=self.annotations,
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
            if url not in self.current_citations:
                self.current_citations.append(url)
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
            await self.put_event(event)

    async def handle_on_token(self, token: ConversationToken):
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

        event = ResponseTextDeltaEvent(
            content_index=self.content_index,
            delta=self.output_delta_buffer,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_text.delta",
            logprobs=[],
        )
        await self.put_event(event)

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

        text = self.current_output_text_content
        delta = ResponseOutputText(
            annotations=self.current_annotations,
            text=text,
            type="output_text",
            logprobs=None,
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
        await self.put_event(event_text_done)

        event_content_part_done = ResponseContentPartDoneEvent(
            content_index=self.content_index,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            part=delta,
            sequence_number=self.manager.sequence_number,
            type="response.content_part.done",
        )
        await self.put_event(event_content_part_done)

        event_output_item_done = ResponseOutputItemDoneEvent(
            item=output_item,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_item.done",
        )
        await self.put_event(event_output_item_done)

        self.manager.manager.browser_tool_used = False
        self.annotations = []
        self.current_output_text_content = ""
        self.output_delta_buffer = ""
        self.debug_full_buffer = ""
        self.current_citations = []

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "ConversationToken"):
        await self.handle_on_token(token)
