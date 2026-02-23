import asyncio
from typing import Union

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.chat.chat_completion import ChatCompletion

from burrito.types.adapter import AdapterCreateParamsChat
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.session_handler import AdapterSessionHandler
from burrito.common.dependencies import (
    get_inference_semaphore,
    get_generation_handler,
    get_session_handler,
)

router = APIRouter()


@router.post("/v1/chat/completions", response_model=ChatCompletion)
async def v1_chat_completions(
    request: Request,
    raw_params: dict,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: AdapterGenerationHandler = Depends(get_generation_handler),
    session_handler: AdapterSessionHandler = Depends(get_session_handler),
) -> Union[StreamingResponse, JSONResponse]:
    try:
        params = AdapterCreateParamsChat(**raw_params)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=422)
    return await run_inference(
        request=request,
        params=params,
        semaphore=semaphore,
        generator=generator,
        session_handler=session_handler,
    )
