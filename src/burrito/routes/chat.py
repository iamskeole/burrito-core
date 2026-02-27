import asyncio
from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.chat.chat_completion import ChatCompletion

from burrito.common.dependencies import (
    get_generation_handler,
    get_inference_semaphore,
    get_session_handler,
)
from burrito.handlers.generation_handler import GenerationHandler
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.session_handler import SessionHandler
from burrito.types.wire_api_params_chat import WireApiParamsChat

router = APIRouter()


@router.post("/v1/chat/completions", response_model=ChatCompletion, tags=["OpenAI"])
async def v1_chat_completions(
    request: Request,
    params: WireApiParamsChat,
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
