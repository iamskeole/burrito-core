import asyncio
from typing import Union

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.responses import Response

from burrito.types.adapter import AdapterCreateParamsResponses
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.common.dependencies import get_inference_semaphore, get_generation_handler

router = APIRouter()


@router.post("/v1/responses", response_model=Response)
async def v1_responses(
    request: Request,
    raw_params: dict,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: AdapterGenerationHandler = Depends(get_generation_handler),
) -> Union[StreamingResponse, JSONResponse]:
    try:
        params = AdapterCreateParamsResponses(**raw_params)
    except Exception as e:
        print(e)
        return JSONResponse(content={"error": str(e)}, status_code=422)
    return await run_inference(
        request=request,
        params=params,
        semaphore=semaphore,
        generator=generator,
    )
