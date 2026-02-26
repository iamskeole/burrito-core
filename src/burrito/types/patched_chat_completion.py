from typing import List, Optional

from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage


# extend so we can use in output json with reasoning + summary
class PatchedChatCompletionChoiceMessage(ChatCompletionMessage):
    reasoning_content: Optional[str] = None
    """The contents of the chunk message."""

    reasoning_summary: Optional[str] = None
    """The summary of the model's reasoning content."""


class PatchedChatCompletionChoice(Choice):
    message: PatchedChatCompletionChoiceMessage  # type: ignore


class PatchedChatCompletion(ChatCompletion):
    choices: List[PatchedChatCompletionChoice]  # type: ignore
