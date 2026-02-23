import asyncio
from typing import Union

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse

# We might need a generic response model or a specific one for Anthropic
# But since we stream or return a dict constructed by plugins/state_handler,
# we can use generic dict or just rely on StreamingResponse / JSONResponse.
# Pydantic model for response validation is good practice though.
# But for now, let's skip response model validation in decorator to avoid
# defining the full response schema if we don't have it handy.
# Or use dictionary.

from burrito.types.adapter import AdapterCreateParamsAnthropic
from burrito.handlers.inference_handler import run_inference
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.session_handler import AdapterSessionHandler
from burrito.common.dependencies import (
    get_inference_semaphore,
    get_generation_handler,
    get_session_handler,
)

router = APIRouter()


# TODO: implement anthropic token counter
@router.post("/v1/messages/count_tokens", response_model=None)
async def v1_count_tokens(request: Request) -> JSONResponse:
    return JSONResponse(content={"error": "Not yet implemented"}, status_code=500)


@router.post("/v1/messages", response_model=None)
async def v1_messages(
    request: Request,
    raw_params: dict,
    semaphore: asyncio.Semaphore = Depends(get_inference_semaphore),
    generator: AdapterGenerationHandler = Depends(get_generation_handler),
    session_handler: AdapterSessionHandler = Depends(get_session_handler),
) -> Union[StreamingResponse, JSONResponse]:
    try:
        params = AdapterCreateParamsAnthropic(**raw_params)
    except Exception as e:
        return JSONResponse(
            content={"error": {"type": "invalid_request_error", "message": str(e)}},
            status_code=422,
        )
    tools = [i["name"] for i in raw_params.get("tools", [])]
    print(tools)
    if not tools:
        print(raw_params["messages"])
    return await run_inference(
        request=request,
        params=params,
        semaphore=semaphore,
        generator=generator,
        session_handler=session_handler,
    )
