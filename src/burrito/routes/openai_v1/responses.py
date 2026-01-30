from typing import Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.responses import Response

from burrito.types.adapter import AdapterCreateParamsResponses
from burrito.handlers.inference_handler import run_inference

router = APIRouter()


@router.post("/v1/responses", response_model=Response)
async def v1_responses(
    request: Request, params: AdapterCreateParamsResponses
) -> Union[StreamingResponse, JSONResponse]:
    # TODO: headers?
    return await run_inference(request=request, params=params)
