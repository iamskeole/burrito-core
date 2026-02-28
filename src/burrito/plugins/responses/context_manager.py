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
from burrito.types.conversation_enums import ConversationState


class ContextManagerPluginResponses(BasePluginResponses):
    def __init__(self, manager):
        super().__init__(manager)

        self.sent_created_event = False
        self.sent_in_progress_event = False

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationState.CREATED,
            ConversationState.IN_PROGRESS,
            ConversationState.COMPLETED,
            ConversationState.TOOL_CALL,
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
            type=f"response.{ConversationState.IN_PROGRESS.value}",  # type: ignore
        )
        await self.put_event(event)
        self.sent_in_progress_event = True

    async def handle_response_completed_event(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected Response, got {type(self.manager.output_object)}"
        )
        self.manager.output_object.status = "completed"

        token_counts = self.get_token_counts()

        self.manager.output_object.usage = ResponseUsage(
            input_tokens=token_counts.n_input,
            input_tokens_details=InputTokensDetails(
                cached_tokens=token_counts.n_cached
            ),
            output_tokens=token_counts.n_completion,
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=sum(
                    [
                        token_counts.n_reasoning,
                        token_counts.n_preamble,
                        token_counts.n_native_tool_input,
                    ]
                )
            ),
            total_tokens=token_counts.n_total,
        )
        for output_item in self.manager.output_object.output:
            if hasattr(output_item, "status"):
                setattr(output_item, "status", "completed")
        event = ResponseCompletedEvent(
            response=self.manager.output_object,
            sequence_number=self.manager.sequence_number,
            type=f"response.{ConversationState.COMPLETED.value}",  # type: ignore
        )
        await self.put_event(event)
        await self.send_close_marker()

    async def on_enter_state(self, state: ConversationState):
        if state == ConversationState.CREATED:
            await self.handle_response_created_event()

        if state == ConversationState.IN_PROGRESS:
            await self.handle_response_in_progress_event()

        if state in [
            ConversationState.COMPLETED,
            ConversationState.TOOL_CALL,
        ]:
            await self.handle_response_completed_event()
