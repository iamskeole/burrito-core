import asyncio
from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.responses import Response

from burrito.common.dependencies import (
    get_generation_handler,
    get_inference_semaphore,
    get_session_handler,
)
from burrito.handlers.generation_handler import GenerationHandler
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.session_handler import SessionHandler
from burrito.types.wire_api_params_responses import WireApiParamsResponses

router = APIRouter()


@router.post("/v1/responses", response_model=Response, tags=["OpenAI"])
async def v1_responses(
    request: Request,
    params: WireApiParamsResponses,
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
