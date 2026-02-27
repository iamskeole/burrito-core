import asyncio
from typing import Union

from anthropic.types.message import Message
from anthropic.types.message_tokens_count import MessageTokensCount
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.common.dependencies import (
    get_generation_handler,
    get_inference_semaphore,
    get_session_handler,
)
from burrito.handlers.generation_handler import GenerationHandler
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.session_handler import SessionHandler
from burrito.services.harmony.harmony_service import (
    build_conversation_from_params,
    render_conversation_for_completion,
)
from burrito.types.wire_api_params_messages import WireApiParamsMessages

router = APIRouter()


@router.post(
    "/v1/messages/count_tokens", response_model=MessageTokensCount, tags=["Anthropic"]
)
async def v1_count_tokens(raw_params: dict) -> Union[MessageTokensCount, JSONResponse]:
    try:
        params = WireApiParamsMessages(**raw_params)
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


@router.post("/v1/messages", response_model=Message, tags=["Anthropic"])
async def v1_messages(
    request: Request,
    params: WireApiParamsMessages,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: GenerationHandler = Depends(get_generation_handler),
    session_handler: SessionHandler = Depends(get_session_handler),
) -> Union[StreamingResponse, JSONResponse]:
    return await run_inference(
        request=request,
        params=params,
        semaphore=semaphore,
        generator=generator,
        session_handler=session_handler,
    )
