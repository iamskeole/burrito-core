import asyncio
from typing import Union

from anthropic.types.message_tokens_count import MessageTokensCount
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.common.dependencies import (
    get_generation_handler,
    get_inference_semaphore,
    get_session_handler,
)
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.session_handler import AdapterSessionHandler
from burrito.services.harmony.harmony_service import (
    build_conversation_from_params,
    render_conversation_for_completion,
)
from burrito.types.adapter import AdapterCreateParamsAnthropic

router = APIRouter()


@router.post("/v1/messages/count_tokens", response_model=None)
async def v1_count_tokens(raw_params: dict) -> MessageTokensCount | JSONResponse:
    try:
        params = AdapterCreateParamsAnthropic(**raw_params)
    except Exception as e:
        return JSONResponse(
            content={"error": {"type": "invalid_request_error", "message": str(e)}},
            status_code=422,
        )
    conversation, _, _, _ = build_conversation_from_params(
        params=params, extra_messages=None
    )
    tokens = render_conversation_for_completion(
        conversation=conversation, is_on_init=True
    )
    result = MessageTokensCount(input_tokens=len(tokens))
    return result


@router.post("/v1/messages", response_model=None)
async def v1_messages(
    request: Request,
    raw_params: dict,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: AdapterGenerationHandler = Depends(get_generation_handler),
    session_handler: AdapterSessionHandler = Depends(get_session_handler),
) -> Union[StreamingResponse, JSONResponse]:
    try:
        params = AdapterCreateParamsAnthropic(**raw_params)
    except Exception as e:
        return JSONResponse(
            content={"error": {"type": "invalid_request_error", "message": str(e)}},
            status_code=422,
        )
    return await run_inference(
        request=request,
        params=params,
        semaphore=semaphore,
        generator=generator,
        session_handler=session_handler,
    )
