from __future__ import annotations

from typing import List, Optional

from openai.types.completion import Completion

from burrito.common.utils import unix_timestamp_in_ms
from burrito.services.harmony import ENCODING, SPECIAL_TOKENS
from burrito.types.conversation_enums import ConversationChannel
from burrito.types.conversation_token import ConversationToken


def create_return_token(
    index: int, finish_reason: str, is_tool_call: bool
) -> ConversationToken:
    return_token = SPECIAL_TOKENS.RETURN if not is_tool_call else SPECIAL_TOKENS.CALL
    token = ConversationToken(
        created_at=unix_timestamp_in_ms(),
        id=return_token.id,
        text=return_token.text,
        index=index,
        finish_reason=finish_reason,
        is_special_token=True,
    )
    return token


def patch_token_finish_reason(
    token: ConversationToken,
    last_parsed_token: Optional[ConversationToken],
    parser_channel: Optional[str],
    parser_recipient: Optional[str],
) -> Optional[ConversationToken]:
    if not last_parsed_token:
        return token  # special case on init when no response tokens
    # llama.cpp only adds <|call|> or <|return|> tokens if logprobs
    # also requested (payload["logprob"] > 0 | != None)
    # instead, it returns a completion with empty text for choices[0],
    # as well as specific finish reason, so we create synthetic token to
    # trigger ConversationState.COMPLETED and finish generation
    if token.id == -1 and token.finish_reason is not None:
        end_token_ids = [SPECIAL_TOKENS.RETURN.id, SPECIAL_TOKENS.CALL.id]

        # happy path where logprobs requested
        if last_parsed_token and last_parsed_token.id in end_token_ids:
            return None
        # unpappy path where llama.cpp does NOT return a <|call|> token, so we
        # need to check if generation ends with a tool call based on parser state
        is_tool_call = (
            parser_channel
            in [
                ConversationChannel.ANALYSIS.value,
                ConversationChannel.COMMENTARY.value,
            ]
            and parser_recipient is not None
        )
        token = create_return_token(token.index, token.finish_reason, is_tool_call)
    return token


def normalize_completion_token(
    completion: Completion,
    response_tokens: List[ConversationToken],
    parser_channel: Optional[str],
    parser_recipient: Optional[str],
) -> Optional[ConversationToken]:
    last_parsed_token = response_tokens[-1] if response_tokens else None
    choice = completion.choices[0]
    text = choice.text
    token_id = -1
    finish_reason = choice.finish_reason

    if choice.logprobs and choice.logprobs.tokens:
        choice_tokens = choice.logprobs.tokens
        token_id = int(choice_tokens[0].split("token_id:")[-1])

    # always encode text, since vLLM exporting tokens is against
    # the official OpenAI spec / type, so we follow the spec
    if token_id == -1 and text is not None:
        # if finish_reason not in ["stop", "length"]:
        tokens = ENCODING.encode(text, allowed_special=("all"))
        if tokens:
            token_id = tokens[0]

    # llama.cpp only returns token id for <|return|>, no text
    if token_id != -1 and not text:
        text = ENCODING.decode([token_id])

    is_special_token = ENCODING.is_special_token(token_id) if token_id != -1 else True
    token = ConversationToken(
        created_at=unix_timestamp_in_ms(),
        id=token_id,
        text=text,
        index=choice.index,
        finish_reason=finish_reason,
        is_special_token=is_special_token,
    )
    return patch_token_finish_reason(
        token, last_parsed_token, parser_channel, parser_recipient
    )
