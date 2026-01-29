from typing import Union

import httpx
from fastapi import Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython

from burrito.handlers.conversation_handler import AdapterConversationHandler
from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.types.adapter import AdapterCreateParams


async def handle_generate(
    request: Request,
    params: AdapterCreateParams,
    generation_handler: AdapterGenerationHandler,
) -> Union[StreamingResponse, JSONResponse]:
    try:
        handler = AdapterConversationHandler(
            request=request,
            params=params,
            generator=generation_handler,
            python_tool=BurritoPython(),
            browser_tool=BurritoBrowser(),
        )
        if params.stream:
            return StreamingResponse(
                content=handler.return_stream(),
                status_code=status.HTTP_200_OK,
                media_type="text/event-stream",
            )
        else:
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
