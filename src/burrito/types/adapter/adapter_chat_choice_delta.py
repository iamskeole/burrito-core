from typing import List, Optional, Dict, Any, Union


from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
)
from openai.types.chat.chat_completion_message import Annotation


# extend so we can use in streaming chunks with reasoning + citations
class AdapterChatChoiceDelta(ChoiceDelta):
    reasoning_content: Optional[str] = None
    """The contents of the chunk message."""

    reasoning_summary: Optional[str] = None
    """The summary of the model's reasoning content."""

    annotations: Optional[List[Annotation]] = None
    """
    Annotations for the message, when applicable, as when using the
    [web search tool](https://platform.openai.com/docs/guides/tools-web-search?api-mode=chat).
    """


class AdapterChatChoice(Choice):
    delta: Union[AdapterChatChoiceDelta, Dict[str, Any]]  # type: ignore


class AdapterChatCompletionChunk(ChatCompletionChunk):
    choices: List[AdapterChatChoice]  # type: ignore
