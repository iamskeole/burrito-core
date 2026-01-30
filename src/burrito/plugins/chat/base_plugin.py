import json
from typing import TYPE_CHECKING, Optional, List

from openai.types.completion_usage import CompletionUsage
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)
from openai.types.chat.chat_completion_message_custom_tool_call import (
    ChatCompletionMessageCustomToolCall,
    Custom,
)


from burrito.types.adapter.adapter_chat_completion_chunk import (
    AdapterChatCompletionChunk,
    AdapterChatCompletionChunkChoice,
)

from burrito.types.adapter.adapter_chat_completion import (
    AdapterChatCompletion,
    AdapterChatCompletionChoice,
    AdapterChatCompletionChoiceMessage,
)

from burrito.common.utils import random_uuid, unix_timestamp, get_system_fingerprint
from burrito.plugins.base_plugin import BasePlugin

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler


class BasePluginChat(BasePlugin):
    def __init__(self, manager: "AdapterStateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.log_extra = {"log_id": f"apr_{self.log_id}"}

    def build_chunk_object(
        self,
        choice: AdapterChatCompletionChunkChoice,
        usage: Optional[CompletionUsage] | None = None,
    ):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], AdapterChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )
        first_chunk = self.manager.output_object[0]
        chunk_object = AdapterChatCompletionChunk(
            id=first_chunk.id,
            created=first_chunk.created,
            object="chat.completion.chunk",
            model=first_chunk.model,
            service_tier=first_chunk.service_tier,
            system_fingerprint=first_chunk.system_fingerprint,
            choices=[choice],
            usage=usage,
        )
        return chunk_object

    def init_response_object(self) -> AdapterChatCompletionChunk:
        init_data = {
            "id": f"chatcmpl-{random_uuid()}",
            "object": "chat.completion.chunk",
            "created": unix_timestamp(),
            "model": self.manager.manager.params.model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}],
            "service_tier": "default",
            "system_fingerprint": f"{get_system_fingerprint()}",
        }
        completion = AdapterChatCompletionChunk(**init_data)
        self.manager.output_object = [completion]
        return completion

    def build_output_object(self) -> AdapterChatCompletion:
        output_arr = self.manager.output_object
        # dumped["object"] = "chat.completion"

        content = ""
        reasoning_content = ""
        tool_call_buffer = []
        tools_called = {}
        tool_calls = []

        for i in output_arr:
            delta = i.choices[0].delta
            if hasattr(delta, "content") and delta.content:
                content += delta.content
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:  # type: ignore
                reasoning_content += delta.reasoning_content  # type: ignore
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                tool_call_buffer += delta.tool_calls

        for i in tool_call_buffer:
            if i.id not in tools_called:
                tools_called[i.id] = {
                    "id": i.id,
                    "name": i.function.name,
                }

                if hasattr(i.function, "arguments"):
                    tools_called[i.id]["arguments"] = i.function.arguments

                if hasattr(i.function, "input"):
                    tools_called[i.id]["input"] = i.function.input
            else:
                if hasattr(i.function, "arguments"):
                    tools_called[i.id]["arguments"] += i.function.arguments

                if hasattr(i.function, "input"):
                    tools_called[i.id]["input"] += i.function.input

        for i in tools_called.values():
            tc = None
            _name, _args, _input = i.get("name"), i.get("arguments"), i.get("input")
            if _args:
                tc = ChatCompletionMessageFunctionToolCall(
                    id="abc",
                    type="function",
                    function=Function(arguments=_args, name=_name),
                )
            if _input:
                tc = ChatCompletionMessageCustomToolCall(
                    id=i["id"], type="custom", custom=Custom(input=_input, name=_name)
                )
            if tc:
                tool_calls.append(tc)

        message = AdapterChatCompletionChoiceMessage(
            content=content,
            reasoning_content=reasoning_content,
            reasoning_summary=None,  # TODO?
            tool_calls=tool_calls,
            role="assistant",
        )

        choice = AdapterChatCompletionChoice(
            index=output_arr[-1].choices[0].index,
            finish_reason=output_arr[-1].choices[0].finish_reason or "stop",
            message=message,
        )
        completion = AdapterChatCompletion(
            id=output_arr[0].id,
            created=output_arr[0].created,
            object="chat.completion",
            model=output_arr[0].model,
            choices=[choice],
            service_tier=output_arr[0].service_tier,
            system_fingerprint=output_arr[0].system_fingerprint,
            usage=output_arr[-1].usage,
        )
        self.manager.output_object.append(completion)

    async def push_event(self, event: AdapterChatCompletionChunk):
        event_data = event.model_dump()
        self.manager.events.append(event_data)

        if self.manager.stream_to_caller:
            encoded = (f"data: {json.dumps(event_data)}\n\n").encode("utf-8")
            await self.manager.push_event(encoded)
