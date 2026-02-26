from typing import Set

from openai.types.responses.response import Response
from openai.types.responses.response_completed_event import ResponseCompletedEvent
from openai.types.responses.response_created_event import ResponseCreatedEvent
from openai.types.responses.response_in_progress_event import ResponseInProgressEvent
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
    ResponseUsage,
)

from burrito.plugins.responses.base_plugin import BasePluginResponses
from burrito.types.enums import ConversationStateEnum


class ContextManagerPluginResponses(BasePluginResponses):
    def __init__(self, manager):
        super().__init__(manager)

        self.sent_created_event = False
        self.sent_in_progress_event = False

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationStateEnum.CREATED,
            ConversationStateEnum.IN_PROGRESS,
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.TOOL_CALL,
        }

    async def handle_response_created_event(self):
        if self.sent_created_event:
            return
        self.init_response_object()
        event = ResponseCreatedEvent(
            response=self.manager.output_object,  # type: ignore
            sequence_number=self.manager.sequence_number,
            type="response.created",
        )
        await self.put_event(event)
        self.sent_created_event = True

    async def handle_response_in_progress_event(self):
        if self.sent_in_progress_event:
            return
        event = ResponseInProgressEvent(
            response=self.manager.output_object,  # type: ignore
            sequence_number=self.manager.sequence_number,
            type=f"response.{ConversationStateEnum.IN_PROGRESS.value}",  # type: ignore
        )
        await self.put_event(event)
        self.sent_in_progress_event = True

    async def handle_response_completed_event(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected Response, got {type(self.manager.output_object)}"
        )
        self.manager.output_object.status = "completed"

        counts = self.get_token_counts()

        self.manager.output_object.usage = ResponseUsage(
            input_tokens=counts.n_input,
            # TODO figure out if possible to get cached counts from backend(s)?
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens=counts.n_completion,
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=sum(
                    [counts.n_reasoning, counts.n_preamble, counts.n_native_tool_input]
                )
            ),
            total_tokens=counts.n_total,
        )
        for output_item in self.manager.output_object.output:
            if hasattr(output_item, "status"):
                setattr(output_item, "status", "completed")
        event = ResponseCompletedEvent(
            response=self.manager.output_object,
            sequence_number=self.manager.sequence_number,
            type=f"response.{ConversationStateEnum.COMPLETED.value}",  # type: ignore
        )
        await self.put_event(event)
        await self.send_close_marker()

    async def on_enter_state(self, state: ConversationStateEnum):
        if state == ConversationStateEnum.CREATED:
            await self.handle_response_created_event()

        if state == ConversationStateEnum.IN_PROGRESS:
            await self.handle_response_in_progress_event()

        if state in [
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.TOOL_CALL,
        ]:
            await self.handle_response_completed_event()
