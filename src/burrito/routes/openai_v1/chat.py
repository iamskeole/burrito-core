import asyncio
from typing import Union

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.types.adapter import AdapterCreateParamsChat
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.common.dependencies import get_inference_semaphore, get_generation_handler

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
async def v1_chat_completions(
    request: Request,
    params: AdapterCreateParamsChat,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: AdapterGenerationHandler = Depends(get_generation_handler),
) -> Union[StreamingResponse, JSONResponse]:
    return await run_inference(
        request=request,
        params=params,
        semaphore=semaphore,
        generator=generator,
    )
