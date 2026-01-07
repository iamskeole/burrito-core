from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.adapter.handlers.state_handler import (
        AdapterStateHandler,
    )
    from burrito.types.adapter import AdapterCompletionToken

from openai.types.responses.response import Response
from openai.types.responses.response_content_part_done_event import (
    PartReasoningText,
    ResponseContentPartDoneEvent,
)
from openai.types.responses.response_output_item_added_event import (
    ResponseOutputItemAddedEvent,
)
from openai.types.responses.response_output_item_done_event import (
    ResponseOutputItemDoneEvent,
)
from openai.types.responses.response_reasoning_item import (
    Content,
    ResponseReasoningItem,
)
from openai.types.responses.response_reasoning_text_delta_event import (
    ResponseReasoningTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_done_event import (
    ResponseReasoningTextDoneEvent,
)

from burrito.plugins.base_plugin_responses import BasePluginResponses
from burrito.common.utils import random_uuid


class ReasoningTextPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.content_index = 0

    @property
    def subscribed_states(self) -> Set[str]:
        return {"reasoning"}

    # TODO: handle content_part_added event
    async def handle_on_enter_state(self):
        self.manager.output_index += 1
        output_item = ResponseReasoningItem(
            id=f"rs_{random_uuid()}",
            summary=[],
            type="reasoning",
            content=[Content(text="", type="reasoning_text")],
            status="in_progress",
        )
        event = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            type="response.output_item.added",
            sequence_number=self.manager.sequence_number,
        )
        await self.push_event(event, output_item)

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        try:
            output_item = self.manager.output_object.output[self.manager.output_index]
        except:
            x = 1

        assert isinstance(output_item, ResponseReasoningItem), (
            f"Expected a ResponseReasoningItem, but got {type(output_item)}"
        )
        assert isinstance(output_item.content, list), (
            f"Expected list[Content], but got {type(output_item.content)}"
        )

        delta = Content(text=token.text, type="reasoning_text")
        event = ResponseReasoningTextDeltaEvent(
            content_index=self.content_index,
            delta=token.text,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.reasoning_text.delta",
        )
        output_item.content.append(delta)
        await self.push_event(event)
        self.content_index += 1

    # TODO: do we override the output_item at the end to only include
    # a single content item with the full reasoning text, or do we leave
    # parts as they got appended?
    # probably leave it as is with a full list of content items, otherwise
    # there would be no point to have that attribute as a list, just add raw text
    # instead of appending to list?
    async def handle_on_exit_state(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]

        assert isinstance(output_item, ResponseReasoningItem), (
            f"Expected a ResponseReasoningItem, but got {type(output_item)}"
        )
        assert isinstance(output_item.content, list), (
            f"Expected list[Content], but got {type(output_item.content)}"
        )
        assert all([isinstance(i, Content) for i in output_item.content]), (
            f"Expected Cintent but got {[type(i) for i in output_item.content]}"
        )

        text = "".join([i.text for i in output_item.content])

        content = Content(text=text, type="reasoning_text")
        delta = PartReasoningText(text=text, type="reasoning_text")
        output_item.content = [content]

        event_reasoning_done = ResponseReasoningTextDoneEvent(
            content_index=self.content_index,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            text=text,
            type="response.reasoning_text.done",
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
        await self.push_event(event_reasoning_done)
        await self.push_event(event_content_part_done)
        await self.push_event(event_output_item_done)

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: AdapterCompletionToken):
        await self.handle_on_token(token)
