from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler

from openai.types.chat.chat_completion_message_custom_tool_call import (
    ChatCompletionMessageCustomToolCall,
    Custom,
)
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)
from openai.types.completion_usage import (
    CompletionTokensDetails,
    CompletionUsage,
)

from burrito.common.utils import (
    get_system_fingerprint,
    random_uuid,
    unix_timestamp,
)
from burrito.plugins.base_plugin import BasePlugin
from burrito.types.patched_chat_completion import (
    PatchedChatCompletion,
    PatchedChatCompletionChoice,
    PatchedChatCompletionChoiceMessage,
)
from burrito.types.patched_chat_completion_chunk import (
    PatchedChatCompletionChunk,
    PatchedChatCompletionChunkChoice,
    PatchedChatCompletionChunkChoiceDelta,
    PatchedChoiceDeltaCustomCallFunction,
    PatchedChoiceDeltaToolCall,
    PatchedChoiceDeltaToolCallFunction,
)


class BasePluginChat(BasePlugin):
    def __init__(self, manager: "StateHandler"):
        super().__init__(manager)
        self.manager = manager
        self.log_extra = {"log_id": f"apr_{self.log_id}"}

    def get_usage_details(self) -> CompletionUsage:
        counts = self.get_token_counts()

        usage = CompletionUsage(
            prompt_tokens=counts.n_input,
            completion_tokens=counts.n_completion,
            total_tokens=counts.n_total,
            completion_tokens_details=CompletionTokensDetails(
                accepted_prediction_tokens=counts.n_completion,
                rejected_prediction_tokens=0,
                reasoning_tokens=sum(
                    [
                        counts.n_reasoning,
                        counts.n_preamble,
                        counts.n_native_tool_input,
                    ]
                ),
            ),
        )
        return usage

    def build_chunk_object(self, choice: PatchedChatCompletionChunkChoice):
        assert isinstance(self.manager.output_object, List), (
            f"Expected a List, but got {type(self.manager.output_object)}"
        )

        assert isinstance(self.manager.output_object[0], PatchedChatCompletionChunk), (
            f"Expected a ChatCompletionChunk, but got {type(self.manager.output_object[0])}"
        )
        first_chunk = self.manager.output_object[0]
        chunk_object = PatchedChatCompletionChunk(
            id=first_chunk.id,
            created=first_chunk.created,
            object="chat.completion.chunk",
            model=first_chunk.model,
            service_tier=first_chunk.service_tier,
            system_fingerprint=first_chunk.system_fingerprint,
            choices=[choice],
            usage=self.get_usage_details(),
        )
        return chunk_object

    def init_response_object(self) -> PatchedChatCompletionChunk:
        init_data = {
            "id": f"chatcmpl-{random_uuid()}",
            "object": "chat.completion.chunk",
            "created": unix_timestamp(),
            "model": self.manager.manager.params.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                }
            ],
            "service_tier": "default",
            "system_fingerprint": f"{get_system_fingerprint()}",
            "usage": self.get_usage_details().model_dump(),
        }
        completion = PatchedChatCompletionChunk(**init_data)
        self.manager.output_object = [completion]
        return completion

    def build_output_object(self) -> None:
        # we build full response here as we're keeping track of
        # streamed tools at the plugin level (state can be improved..)
        # so return_json has a full object to just .model_dump()
        if self.manager.stream_to_caller:
            return
        assert isinstance(self.manager.output_object, list), (
            f"Expected list, got {type(self.manager.output_object)}"
        )

        output_arr = self.manager.output_object
        content = ""
        reasoning_content = ""
        tool_call_buffer: List[PatchedChoiceDeltaToolCall] = []
        tools_called = {}
        tool_calls = []

        for chunk in output_arr:
            assert isinstance(chunk, PatchedChatCompletionChunk), (
                f"Expected AdapterChatCompletionChunk, got {type(chunk)}"
            )
            delta = chunk.choices[0].delta
            if isinstance(delta, dict):
                continue  # first and last deltas are empty dicts..
            assert isinstance(delta, PatchedChatCompletionChunkChoiceDelta), (
                f"Expected AdapterChatCompletionChunkChoiceDelta, got {type(delta)}"
            )
            if delta.content:
                content += delta.content
            if delta.reasoning_content:
                reasoning_content += delta.reasoning_content
            if delta.tool_calls:
                tool_call_buffer += delta.tool_calls

        # matching official openai implementation, keyed by idnex
        # see https://platform.openai.com/docs/guides/function-calling?api-mode=chat
        for part in tool_call_buffer:
            assert part.function is not None, "Expected a function, got None."
            if part.index not in tools_called:
                tools_called[part.index] = {
                    "index": part.index,
                    "id": part.id,
                    "name": part.function.name,
                    "type": part.type,
                    "content": "",
                }
            match part.function:
                case PatchedChoiceDeltaToolCallFunction():
                    tools_called[part.index]["content"] += part.function.arguments
                case PatchedChoiceDeltaCustomCallFunction():
                    tools_called[part.index]["content"] += part.function.input
                case _:
                    raise TypeError(
                        "Expected "
                        "`AdapterChoiceDeltaToolCallFunction` or "
                        "`AdapterChoiceDeltaCustomCallFunction`, "
                        f"got {type(part)}"
                    )

        for i in tools_called.values():
            tc = None
            _id, _name, _type, _content = (
                i["id"],
                i["name"],
                i["type"],
                i["content"],
            )

            match _type:
                case "function":
                    tc = ChatCompletionMessageFunctionToolCall(
                        id=_id,
                        type=_type,
                        function=Function(arguments=_content, name=_name),
                    )
                case "custom":
                    tc = ChatCompletionMessageCustomToolCall(
                        id=i["id"],
                        type="custom",
                        custom=Custom(input=_content, name=_name),
                    )
                case _:
                    raise TypeError(f"Expected `function` or `custom`, got {_type}")
            if tc:
                tool_calls.append(tc)

        message = PatchedChatCompletionChoiceMessage(
            content=content,
            reasoning_content=reasoning_content,
            reasoning_summary=None,  # TODO implement reasoning_text_summary plugin?
            tool_calls=tool_calls,
            role="assistant",
        )

        choice = PatchedChatCompletionChoice(
            index=output_arr[-1].choices[0].index,
            finish_reason=output_arr[-1].choices[0].finish_reason or "stop",
            message=message,
        )
        completion = PatchedChatCompletion(
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
