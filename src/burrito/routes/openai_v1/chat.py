from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.common.dependencies import AdapterGenerationHandler, get_generation_handler
from burrito.types.adapter import AdapterCreateParamsChat, AdapterRequestCategory

from ._handle_generate import handle_generate

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
async def v1_responses(
    request: Request,
    params: AdapterCreateParamsChat,
    generation_handler: AdapterGenerationHandler = Depends(get_generation_handler),
) -> Union[StreamingResponse, JSONResponse]:
    return await handle_generate(
        request=request,
        params=params,
        category=AdapterRequestCategory.CHAT,
        generation_handler=generation_handler,
    )
