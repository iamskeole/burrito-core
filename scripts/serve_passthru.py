import json

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from burrito import __version__
from burrito.common.config import settings
from burrito.common.utils import get_headers_to_forward

app = FastAPI(title="burrito:passthru", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS.split(","),
    allow_methods=settings.CORS_ALLOWED_METHODS.split(","),
    allow_headers=settings.CORS_ALLOWED_HEADERS.split(","),
    allow_credentials=settings.CORS_ALLOWED_CREDENTIALS,
)

client = httpx.AsyncClient(
    base_url=settings.BACKEND_BASE_URL, timeout=settings.BACKEND_INTER_TOKEN_TIMEOUT
)


async def proxy_post_request(request: Request, path: str):
    payload = await request.json()
    payload["skip_special_tokens"] = False
    payload["include_stop_str_in_output"] = True
    payload["spaces_between_special_tokens"] = True
    payload["return_tokens_as_token_ids"] = True
    payload["return_token_ids"] = True

    is_streaming_request = payload.get("stream", False)
    url = httpx.URL(path=path, query=request.url.query.encode("utf-8"))
    headers = get_headers_to_forward(request)

    if is_streaming_request:
        backend_request = client.build_request(
            request.method, url, headers=headers, json=payload
        )
        backend_response = await client.send(backend_request, stream=True)

        async def response_generator():
            all_chunks = []
            acc_eventstrings = []
            acc_datastrings = []
            acc_loadedstrings = []
            acc_err_strings = []
            async for chunk in backend_response.aiter_raw():
                if settings.DEBUG_COMPLETIONS:
                    print(chunk)
                all_chunks.append(chunk.decode("utf-8"))

                dec = chunk.decode()
                split = dec.split("\n")

                for i in split:
                    if i.startswith("event"):
                        acc_eventstrings.append(i)
                    elif i.startswith("data"):
                        acc_datastrings.append(i)
                        try:
                            loaded = json.loads(i[6:])
                            acc_loadedstrings.append(loaded)
                        except json.JSONDecodeError:
                            acc_err_strings.append(i)
                yield chunk
            await backend_response.aclose()

        return StreamingResponse(
            response_generator(),
            status_code=backend_response.status_code,
            headers=backend_response.headers,
        )
    else:
        backend_response = await client.request(
            request.method, url, headers=headers, json=payload
        )
        return Response(
            content=backend_response.content,
            status_code=backend_response.status_code,
            headers=backend_response.headers,
        )


@app.get("/v1/models")
async def proxy_models(request: Request):
    headers = get_headers_to_forward(request)
    backend_response = await client.get("/v1/models", headers=headers)

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers=backend_response.headers,
    )


@app.post("/v1/messages")
async def proxy_messages(request: Request):
    return await proxy_post_request(request, "/v1/messages")


@app.post("/v1/chat/completions")
async def proxy_chat(request: Request):
    return await proxy_post_request(request, "/v1/chat/completions")


@app.post("/v1/completions")
async def proxy_completions(request: Request):
    return await proxy_post_request(request, "/v1/completions")


@app.post("/v1/responses")
async def proxy_responses(request: Request):
    return await proxy_post_request(request, "/v1/responses")


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
