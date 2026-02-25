from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler
    from burrito.types.adapter import AdapterCompletionToken

from openai.types.responses.response import Response
from openai.types.responses.response_content_part_added_event import (
    PartReasoningText as PartReasoningTextAdded,
)
from openai.types.responses.response_content_part_added_event import (
    ResponseContentPartAddedEvent,
)
from openai.types.responses.response_content_part_done_event import (
    PartReasoningText as PartReasoningTextDone,
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

from burrito.common.utils import random_uuid
from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.types.adapter import AdapterConversationState


class ReasoningTextPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        # hardcoded, not incremented, to match gpt-oss reference implementation
        # only one content item, which means somehow multiple are allowed in .content=[]?
        self.content_index = 0

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            # NOTE: if we comment out .REASONING, only shows preamble to users
            # this is the official guideline for gpt-oss, but since we're
            # running locally, responsibility should be client's, we expose
            # everything here so caller can decide ui stuff
            AdapterConversationState.REASONING,
            AdapterConversationState.PREAMBLE,
        }

    async def handle_on_enter_state(self):
        output_object = self.manager.output_object
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(output_object)}"
        )
        self.manager.output_index += 1
        output_item = ResponseReasoningItem(
            id=f"rs_{random_uuid()}",
            summary=[],
            type="reasoning",
            content=[],
            status="in_progress",
        )
        event_item = ResponseOutputItemAddedEvent(
            item=output_item,
            output_index=self.manager.output_index,
            type="response.output_item.added",
            sequence_number=self.manager.sequence_number,
        )
        self.manager.output_object.output.append(output_item)
        await self.put_event(event_item)

        # sending blank text on content part added, per the reference
        # implementation (api_server.py in gpt-oss responses)
        event_content = ResponseContentPartAddedEvent(
            type="response.content_part.added",
            content_index=self.content_index,
            output_index=self.manager.output_index,
            item_id=output_item.id,
            part=PartReasoningTextAdded(text="", type="reasoning_text"),
            sequence_number=self.manager.sequence_number,
        )
        await self.put_event(event_content)

    async def handle_on_token(self, token: AdapterCompletionToken):
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

        event = ResponseReasoningTextDeltaEvent(
            content_index=self.content_index,
            delta=token.text,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.reasoning_text.delta",
        )
        await self.put_event(event)

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

        try:
            text = self.manager.conversation.messages[-1].content[0].text  # type: ignore
        except IndexError:
            # should not happen?
            # fixed by setting manager parser state to error on _recover_state()
            msg = "handle_on_exit_state: missing parser messages."
            self.logger.error(msg, extra=self.log_extra)
            text = ""

        content = Content(text=text, type="reasoning_text")
        delta = PartReasoningTextDone(text=text, type="reasoning_text")
        output_item.content = [content]
        output_item.status = "completed"

        event_reasoning_done = ResponseReasoningTextDoneEvent(
            content_index=self.content_index,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            text=text,
            type="response.reasoning_text.done",
        )
        await self.put_event(event_reasoning_done)

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

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: AdapterCompletionToken):
        await self.handle_on_token(token)
