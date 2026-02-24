import asyncio
from typing import Union

import httpx
from fastapi import Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.common.config import settings
from burrito.handlers.conversation_handler import AdapterConversationHandler
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.handlers.session_handler import AdapterSessionHandler
from burrito.types.adapter import AdapterCreateParams


# TODO: non-stream should also disconnect when client disconnects
async def run_inference(
    request: Request,
    params: AdapterCreateParams,
    semaphore: asyncio.Semaphore,
    generator: AdapterGenerationHandler,
    session_handler: AdapterSessionHandler,
) -> Union[StreamingResponse, JSONResponse]:
    forwarded_headers = {
        k: v
        for k, v in request.headers.items()
        if k.title() in [h.title() for h in settings.FORWARD_HEADERS]
    }

    async def stream_with_semaphore(handler: AdapterConversationHandler):
        async with semaphore:
            async for chunk in handler.return_stream():
                yield chunk

    try:
        handler = AdapterConversationHandler(
            request=request,
            params=params,
            generator=generator,
            session_handler=session_handler,
            forwarded_headers=forwarded_headers,
        )
        if params.stream:
            return StreamingResponse(
                content=stream_with_semaphore(handler),
                status_code=status.HTTP_200_OK,
                media_type="text/event-stream",
            )
        else:
            async with semaphore:
                return JSONResponse(
                    content=await handler.return_json(),
                    status_code=status.HTTP_200_OK,
                    media_type="application/json",
                )

    except httpx.HTTPStatusError as exc:
        status_code, status_text = exc.response.status_code, exc.response.text
        msg = f"Backend returned status {status_code}: {status_text}"
        error_json = {
            "error": {
                "message": msg,
                "type": "backend_error",
                "status": status_code,
            }
        }
        return JSONResponse(
            error_json,
            status_code=status_code,
            media_type="application/json",
        )

    except httpx.RequestError as exc:
        error_json = {
            "error": {
                "message": f"Connection error: {str(exc)}",
                "type": "connection_error",
                "status": 502,
            }
        }
        return JSONResponse(
            error_json,
            status_code=502,
            media_type="application/json",
        )

    except Exception as exc:
        error_json = {
            "error": {
                "message": f"Internal error: {str(exc)}",
                "type": "internal_error",
                "status": 500,
            }
        }
        return JSONResponse(
            error_json,
            status_code=500,
            media_type="application/json",
        )
