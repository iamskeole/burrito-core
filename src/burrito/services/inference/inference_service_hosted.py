import json
from typing import AsyncGenerator, Dict, Union

import httpx
from openai.types.completion import Completion
from openai.types.completion_choice import CompletionChoice, Logprobs
from openai.types.completion_create_params import (
    CompletionCreateParamsBase,
    CompletionCreateParamsStreaming,
)

from burrito.common.config import settings
from burrito.types.adapter import AdapterCreateParams

BACKEND_BASE_URL = settings.INFERENCE_BACKEND_BASE_URL
BACKEND_COMPLETIONS_PATH = settings.INFERENCE_BACKEND_COMPLETIONS_PATH


# TODO: handle cases where choices n > 1
def map_completion_data(data: Dict, text_offset: int) -> Completion | None:
    # we exit if no logprobs, since we need logprobs to extract token ids
    choice_dict = data["choices"][0]
    logprobs: dict = choice_dict.get("logprobs")
    finish_reason = choice_dict.get("finish_reason")
    # if not logprobs and finish_reason not in ["stop", "length"]:
    #     return None

    # OpenAI spec seems wrong for completion? requires Literal finish_reason even
    # when completions are in progress, so we hack that here
    filler_reason = "content_filter"
    if choice_dict["finish_reason"] is None:
        choice_dict["finish_reason"] = filler_reason

    completion = Completion(**data)
    choice: CompletionChoice = completion.choices[0]

    # and here we reverse the hack..
    if choice.finish_reason is filler_reason:
        choice.finish_reason = None  # type: ignore

    if not logprobs and finish_reason in ["stop", "length"]:
        return completion

    # vllm matches OpenAI type, we're standardizing llama.cpp to that as well
    # {
    #     'text_offset': [0],
    #     'token_logprobs': [0.0],
    #     'tokens': ['token_id:200005'],
    #     'top_logprobs': [{'token_id:200005': 0.0, 'token_id:220': -23.375, ...}]
    # }
    # NOTE: vllm also has some way of returning raw tokens but it does so in a
    # way that's not compatible with the OpenAI type, so we're taking a small
    # hit in splitting token_id:xx strings to keep in line with official spec
    if logprobs and logprobs.get("tokens", []):
        pass  # vllm handles properly

    # llama.cpp with logprobs
    elif logprobs and logprobs.get("content", []):
        token_logprob_data = logprobs["content"][0]
        token_id = token_logprob_data["id"]
        token_id_str = f"token_id:{token_id}"
        token_logprob = token_logprob_data["logprob"]
        candidates = token_logprob_data["top_logprobs"]

        choice.logprobs = Logprobs(
            text_offset=[text_offset],
            token_logprobs=[token_logprob],
            tokens=[token_id_str],
            top_logprobs=[],
        )

        for candidate in candidates:
            candidate_token_id = candidate["id"]
            candidate_token_logprob = candidate["logprob"]
            candidate_id_str = f"token_id:{candidate_token_id}"
            candidate_data = {candidate_id_str: candidate_token_logprob}
            if choice.logprobs.top_logprobs is not None:
                choice.logprobs.top_logprobs.append(candidate_data)
    return completion


# TODO remove hack with responses request type, add a proxy with completions too
def build_payload(
    prompt_token_ids: list[int], params: AdapterCreateParams
) -> CompletionCreateParamsBase:
    default_keys = CompletionCreateParamsBase.__annotations__.keys()
    payload_default = CompletionCreateParamsBase(
        model=params.model,
        prompt=prompt_token_ids,
    )

    # capture any non-pydantic / required params sent by caller
    params_dumped = params.model_dump()

    for k, v in params_dumped.items():
        if v and k in default_keys:
            payload_default[k] = v

    ctx_len = settings.DEFAULT_MODEL_CTX_LEN
    max_tokens_params = max(
        params_dumped.get("max_completion_tokens") or 0,
        params_dumped.get("max_output_tokens") or 0,
        params_dumped.get("max_tokens") or 0,
    )
    max_tokens_possible = ctx_len - len(prompt_token_ids)
    max_tokens = min(max_tokens_params, max_tokens_possible)

    payload_default["max_tokens"] = max_tokens or max_tokens_possible

    payload = CompletionCreateParamsStreaming(**payload_default, stream=True)

    # TODO: figure out hitting max model length here + errors (it WILL crash)

    # default to logprobs for both vLLM and llama.cpp
    # WARNING: llama.cpp inference speed drops 3x as of 9.29.25 when logprobs >0
    # vLLM is less sensitive, seems to be unaffected by None, 0 or 20 logprobs
    payload["logprobs"] = None #20

    # --- overrides, we ignore anything the caller sends here to preserve format

    # vLLM - include all tokens, we're processing locally
    payload["skip_special_tokens"] = False  # type: ignore
    payload["include_stop_str_in_output"] = True  # type: ignore
    payload["spaces_between_special_tokens"] = False  # type: ignore

    # force vLLM to return token ids instead of text only
    payload["return_tokens_as_token_ids"] = True  # type: ignore
    payload["return_token_ids"] = True  # type: ignore
    return payload


async def generate_hosted(
    prompt_token_ids: list[int],
    params: AdapterCreateParams,
    headers: Dict[str, str] = {},
) -> AsyncGenerator[Union[Completion, Dict, str], None]:
    url = BACKEND_BASE_URL.rstrip("/") + "/" + BACKEND_COMPLETIONS_PATH.lstrip("/")
    payload = build_payload(prompt_token_ids, params)

    response_buffer = ""  # TODO: cleanup, debug only
    # TODO try / except here, to catch unresponsive backend before post?

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            response.raise_for_status()

            message_buffer = ""
            data = {}
            text_offset = 0

            async for line in response.aiter_lines():
                if not line:
                    if message_buffer:
                        try:
                            if message_buffer.strip() == "[DONE]":
                                yield message_buffer
                                break
                            data = json.loads(message_buffer)
                        except json.JSONDecodeError:
                            # keep incrementing buffer, invisible to caller
                            # not yielding error message as it's just not
                            # accumulated a full, correct, data dict yet
                            pass
                        try:
                            # TODO: here, there will be no "choices" key
                            # on request exceeding context size; leave it to
                            # throw an error for now, but figure out how to handle
                            # ideally i think we need to catch before calling
                            # backend and throw a nice error to the caller
                            # that their prompt exceeds model capacity
                            # BUT it will probably happen in generation as well?
                            # so we need to make sure payload max tokens is
                            # computed correctly based on len(prompt_tokens)
                            # and model capacity
                            # TODO: model capacity - get from backend instead
                            # of using a config var? logic here being the user
                            # of the harness may decide they wish to serve
                            # lower context length for various reasons (eg higher
                            # concurrency at lower ctx), so check to see if
                            # backend exposes that in /v1/models call
                            # should we just surface the error and throw so
                            # generator stops and caller gets backend error verbatim?
                            # TODO: see how both vllm and llamacpp handle this
                            # NOTE: llamacpp: "data: {'error': {
                            # 'code': 400,
                            # 'message': 'the request exceeds the available context size.
                            # try increasing the context size or enable context shift',
                            # 'type': 'exceed_context_size_error',
                            # 'n_prompt_tokens': 132298,
                            # 'n_ctx': 131072}}
                            # \ntext_offset: 0"
                            if not data["choices"]:
                                yield "[DONE]"
                                break  # vllm sending usage on last message with no choices
                            completion = map_completion_data(data, text_offset)
                            response_buffer += completion.choices[0].text
                            # typically to catch llama.cpp NOT sending
                            # finish_reason on last completion, but adding a
                            # new completion without an actual token attached
                            assert completion is not None, (
                                f"Failed to build completion: {data}"
                            )
                            assert len(completion.choices) > 0, (
                                f"Completion missing choices: {data}"
                            )
                            # we only reset buffer for next message only after
                            # completion mapped successfully; until that happens,
                            # it's likely we're still accumulating lines inside
                            # the message buffer
                            message_buffer = ""
                            text_offset += len(completion.choices[0].text)
                            yield completion
                        except Exception as e:
                            # raise here to break the main processing loop
                            # and return an exception to the caller
                            msg = (
                                f"map_completion_data: {repr(e)}",
                                f"data: {data}\ntext_offset: {text_offset}",
                            )
                            raise Exception(msg)

                if line.startswith("data:"):
                    raw_data = line[len("data: ") :]
                    if raw_data.strip() == "[DONE]":
                        yield raw_data
                        break
                    message_buffer += raw_data  #
