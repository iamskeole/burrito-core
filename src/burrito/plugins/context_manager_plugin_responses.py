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

from burrito.types.adapter import AdapterConversationState

from .base_plugin_responses import BasePluginResponses


class ContextManagerPluginResponses(BasePluginResponses):
    def __init__(self, manager):
        super().__init__(manager)

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            AdapterConversationState.CREATED,
            AdapterConversationState.IN_PROGRESS,
            AdapterConversationState.COMPLETED,
            AdapterConversationState.TOOL_CALL,
        }

    async def handle_response_created_event(self):
        self.init_response_object()
        event = ResponseCreatedEvent(
            response=self.manager.output_object,  # type: ignore
            sequence_number=self.manager.sequence_number,
            type=f"response.{AdapterConversationState.CREATED.value}",  # type: ignore
        )
        await self.push_event(event)

    async def handle_response_in_progress_event(self):
        event = ResponseInProgressEvent(
            response=self.manager.output_object,  # type: ignore
            sequence_number=self.manager.sequence_number,
            type=f"response.{AdapterConversationState.IN_PROGRESS.value}",  # type: ignore
        )
        await self.push_event(event)

    async def handle_response_completed_event(self):
        assert isinstance(self.manager.output_object, Response), (
            f"Expected Response, got {type(self.manager.output_object)}"
        )
        self.manager.output_object.status = "completed"

        n_input_tokens = len(self.manager.prompt_tokens)
        n_reasoning_tokens = len(self.manager.reasoning_tokens)
        n_output_tokens = len(self.manager.response_tokens)

        self.manager.output_object.usage = ResponseUsage(
            input_tokens=n_input_tokens,
            input_tokens_details=InputTokensDetails(cached_tokens=0),  # TODO
            output_tokens=n_output_tokens,
            output_tokens_details=OutputTokensDetails(
                reasoning_tokens=n_reasoning_tokens
            ),
            total_tokens=n_input_tokens + n_output_tokens,
        )
        event = ResponseCompletedEvent(
            response=self.manager.output_object,  # type: ignore
            sequence_number=self.manager.sequence_number,
            type=f"response.{AdapterConversationState.COMPLETED.value}",  # type: ignore
        )
        for output_item in self.manager.output_object.output:
            if hasattr(output_item, "status"):
                setattr(output_item, "status", "completed")
        await self.push_event(event)

    async def on_enter_state(self, state: AdapterConversationState):
        if state in [
            AdapterConversationState.COMPLETED,
            AdapterConversationState.TOOL_CALL,
        ]:
            await self.handle_response_completed_event()

        elif (
            state == AdapterConversationState.CREATED
            and not self.manager.created_event_fired
        ):
            await self.handle_response_created_event()

        elif (
            state == AdapterConversationState.IN_PROGRESS
            and not self.manager.created_event_fired
        ):
            await self.handle_response_in_progress_event()
