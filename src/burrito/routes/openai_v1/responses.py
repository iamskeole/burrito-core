from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.responses import Response

from burrito.common.dependencies import (
    AdapterGenerationHandler,
    SandboxHandler,
    get_generation_handler,
    get_sandbox_handler,
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
    sandbox_handler: SandboxHandler = Depends(get_sandbox_handler),
) -> Union[StreamingResponse, JSONResponse]:
    jsn = await request.json()
    import json
    # print('=' * 100)
    # print("tools")
    # print(json.dumps(raw_params["tools"], indent=2))
    # print('=' * 100)
    # print("inputs")
    # print(json.dumps(raw_params["input"], indent=2))
    # try:
    #     params = ProxyCreateParamsResponses(**raw_params)
    # except Exception as e:
    #     print(e)
    #     return
    return await handle_generate(
        request=request,
        params=params,
        generation_handler=generation_handler,
        sandbox_handler=sandbox_handler,
    )
