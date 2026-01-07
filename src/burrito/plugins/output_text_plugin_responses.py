from __future__ import annotations

from typing import TYPE_CHECKING, Set

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
from openai.types.responses.response_output_text import ResponseOutputText
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent

from burrito.plugins.base_plugin_responses import BasePluginResponses
from burrito.common.utils import random_uuid


class OutputTextPluginResponses(BasePluginResponses):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.content_index = 0

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

    async def handle_on_token(self, token: AdapterCompletionToken):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected a Response, but got {type(self.manager.output_object)}"
        )

        output_item = self.manager.output_object.output[self.manager.output_index]
        assert isinstance(output_item, ResponseOutputMessage), (
            f"Expected a ResponseOutputMessage, but got {type(output_item)}"
        )

        # TODO: figure out annotations
        delta = ResponseOutputText(
            annotations=[], text=token.text, type="output_text", logprobs=None
        )
        event = ResponseTextDeltaEvent(
            content_index=self.content_index,
            delta=token.text,
            item_id=output_item.id,
            output_index=self.manager.output_index,
            sequence_number=self.manager.sequence_number,
            type="response.output_text.delta",
            logprobs=[],
        )

        output_item.content.append(delta)
        await self.push_event(event)
        self.content_index += 1

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

    async def on_enter_state(self, state: str):
        await self.handle_on_enter_state()

    async def on_exit_state(self, state: str):
        await self.handle_on_exit_state()

    async def on_token(self, token: "AdapterCompletionToken"):
        await self.handle_on_token(token)
