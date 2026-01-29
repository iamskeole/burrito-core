from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.responses import Response

from burrito.common.dependencies import (
    AdapterGenerationHandler,
    get_generation_handler,
)
from burrito.types.adapter import AdapterCreateParamsResponses

from ._handle_generate import handle_generate

router = APIRouter()


@router.post("/v1/responses", response_model=Response)
async def v1_responses(
    request: Request,
    params: AdapterCreateParamsResponses,
    # raw_params: dict,
    generation_handler: AdapterGenerationHandler = Depends(get_generation_handler),
) -> Union[StreamingResponse, JSONResponse]:
    jsn = await request.json()
    import json
    # try:
    #     params = ProxyCreateParamsResponses(**raw_params)
    # except Exception as e:
    #     print(e)
    #     return
    return await handle_generate(
        request=request,
        params=params,
        generation_handler=generation_handler,
    )
