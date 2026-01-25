from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.responses import Response

from burrito.common.dependencies import (
    AdapterGenerationHandler,
    PythonTool,
    BurritoBrowser,
    get_generation_handler,
    get_python_tool,
    get_browser_tool,
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
    # python_tool: PythonTool = Depends(get_python_tool),
    # browser_tool: BurritoBrowser = Depends(get_browser_tool),
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
        # init both on every route instead of depends for session separation
        # otherwise agent gets confused if it has full list of sites visited
        # across sessions (indices get fucked)
        python_tool=PythonTool(),
        browser_tool=BurritoBrowser(),
    )
