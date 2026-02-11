from typing import Set

from burrito.plugins.anthropic.base_plugin import BasePluginAnthropic
from burrito.types.adapter import AdapterConversationState
from pydantic import BaseModel

from anthropic.types.message import Message
from anthropic.types.message_start_event import MessageStartEvent
from anthropic.types.message_delta_event import MessageDeltaEvent
from anthropic.types.message_stop_event import MessageStopEvent
from anthropic.types.message_delta_usage import MessageDeltaUsage
from anthropic.types.raw_message_delta_event import Delta
from anthropic.types.stop_reason import StopReason


class ContextManagerPluginAnthropic(BasePluginAnthropic):
    def __init__(self, manager):
        super().__init__(manager)

        self.sent_start_event = False

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            AdapterConversationState.CREATED,
            AdapterConversationState.IN_PROGRESS,
            AdapterConversationState.COMPLETED,
            AdapterConversationState.TOOL_CALL,
        }

    async def handle_message_start_event(self):
        if self.sent_start_event:
            return
        self.init_response_object()
        message = self.manager.output_object
        event = MessageStartEvent(
            type="message_start",
            message=message,  # type: ignore
        )
        await self.put_event(event)
        self.sent_start_event = True

    async def handle_message_stop_event(self, state: AdapterConversationState):
        token_counts = self.get_token_counts()
        stop_reason = "end_turn"
        if state == AdapterConversationState.TOOL_CALL:
            stop_reason = "tool_use"

        event_delta = MessageDeltaEvent(
            type="message_delta",
            delta=Delta(
                stop_reason=stop_reason  # type: ignore
            ),
            usage=MessageDeltaUsage(
                input_tokens=token_counts.n_input,
                output_tokens=token_counts.n_completion,
            ),
        )
        event_stop = MessageStopEvent(type="message_stop")
        await self.put_event(event_delta)
        await self.put_event(event_stop)
        await self.send_close_marker()

    async def on_enter_state(self, state: AdapterConversationState):
        if state == AdapterConversationState.CREATED:
            await self.handle_message_start_event()

        if state in [
            AdapterConversationState.COMPLETED,
            AdapterConversationState.TOOL_CALL,
        ]:
            await self.handle_message_stop_event(state)
