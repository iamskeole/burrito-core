from typing import Set

from anthropic.types.message_delta_usage import MessageDeltaUsage
from anthropic.types.raw_message_delta_event import Delta, RawMessageDeltaEvent
from anthropic.types.raw_message_start_event import RawMessageStartEvent
from anthropic.types.raw_message_stop_event import RawMessageStopEvent

from burrito.plugins.messages.base_plugin import BasePluginMessages
from burrito.types.conversation_enums import ConversationState


class ContextManagerPluginMessages(BasePluginMessages):
    def __init__(self, manager):
        super().__init__(manager)

        self.sent_start_event = False

    @property
    def subscribed_states(self) -> Set[str]:
        return {
            ConversationState.CREATED,
            ConversationState.IN_PROGRESS,
            ConversationState.COMPLETED,
            ConversationState.TOOL_CALL,
        }

    async def handle_message_start_event(self):
        if self.sent_start_event:
            return
        self.init_response_object()
        message = self.manager.output_object
        event = RawMessageStartEvent(
            type="message_start",
            message=message,  # type: ignore
        )
        await self.put_event(event)
        self.sent_start_event = True

    async def handle_message_stop_event(self, state: ConversationState):
        token_counts = self.get_token_counts()
        stop_reason = "end_turn"
        if state == ConversationState.TOOL_CALL:
            stop_reason = "tool_use"

        event_delta = RawMessageDeltaEvent(
            type="message_delta",
            delta=Delta(
                stop_reason=stop_reason  # type: ignore
            ),
            usage=MessageDeltaUsage(
                input_tokens=token_counts.n_input,
                output_tokens=token_counts.n_completion,
            ),
        )
        event_stop = RawMessageStopEvent(type="message_stop")
        await self.put_event(event_delta)
        await self.put_event(event_stop)
        await self.send_close_marker()

    async def on_enter_state(self, state: ConversationState):
        if state == ConversationState.CREATED:
            await self.handle_message_start_event()

        if state in [
            ConversationState.COMPLETED,
            ConversationState.TOOL_CALL,
        ]:
            await self.handle_message_stop_event(state)
