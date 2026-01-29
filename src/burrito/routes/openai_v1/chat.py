from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.common.dependencies import AdapterGenerationHandler, get_generation_handler
from burrito.types.adapter import AdapterCreateParamsChat

from ._handle_generate import handle_generate

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
async def v1_chat_completions(
    request: Request,
    raw_params: dict,
    # params: AdapterCreateParamsChat,
    generation_handler: AdapterGenerationHandler = Depends(get_generation_handler),
) -> Union[StreamingResponse, JSONResponse]:
    jsn = await request.json()
    import json

    try:
        params = AdapterCreateParamsChat(**raw_params)
    except Exception as e:
        print(e)
        x = 1

    return await handle_generate(
        request=request,
        params=params,
        generation_handler=generation_handler,
    )
