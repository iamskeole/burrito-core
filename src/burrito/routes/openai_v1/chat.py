from typing import Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.types.adapter import AdapterCreateParamsChat
from burrito.handlers.inference_handler import run_inference

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
async def v1_chat_completions(
    request: Request,
    params: AdapterCreateParamsChat,
) -> Union[StreamingResponse, JSONResponse]:
    # TODO: headers?
    return await run_inference(request=request, params=params)
