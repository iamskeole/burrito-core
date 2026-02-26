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
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.session_handler import AdapterSessionHandler
from burrito.types.create_params_responses import CreateParamsResponses

router = APIRouter()


@router.post("/v1/responses", response_model=Response)
async def v1_responses(
    request: Request,
    raw_params: dict,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: AdapterGenerationHandler = Depends(get_generation_handler),
    session_handler: AdapterSessionHandler = Depends(get_session_handler),
) -> Union[StreamingResponse, JSONResponse]:
    try:
        params = CreateParamsResponses(**raw_params)
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
