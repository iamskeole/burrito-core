import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response

# --- Configuration ---
# Set the base URL of your OpenAI-compatible backend.
# You can also set this via an environment variable named 'BACKEND_URL'.
# For Azure, this would be something like "https://YOUR-RESOURCE-NAME.openai.azure.com/openai"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://apollo.local:9999")

# --- FastAPI Application ---
app = FastAPI(
    title="OpenAI Compatible Proxy",
    description="A FastAPI proxy for OpenAI compatible backends. It handles /v1/models, /v1/chat/completions, /v1/completions, and /v1/responses endpoints.",
    version="4.0.0",
)

# --- HTTP Client ---
# We use a single httpx.AsyncClient instance to reuse connections and improve performance.
# A longer timeout is added to accommodate potentially slow model responses.
client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=300.0)


# --- Unified POST Proxy Logic ---
async def proxy_post_request(request: Request, path: str):
    """
    This function proxies POST requests to the backend, intelligently handling both
    streaming and non-streaming responses based on the request payload.
    """
    # 1. Read the request body. This is necessary to inspect it for the 'stream' flag.
    payload = await request.json()
    payload["skip_special_tokens"] = False
    payload["include_stop_str_in_output"] = True
    payload["spaces_between_special_tokens"] = True
    payload["return_tokens_as_token_ids"] = True
    payload["return_token_ids"] = True

    # 2. Check if the request is for streaming.
    is_streaming_request = payload.get("stream", False)

    # 3. Prepare the request to be sent to the backend.
    url = httpx.URL(path=path, query=request.url.query.encode("utf-8"))

    # Forward relevant headers from the original request.
    headers = {
        key: value for key, value in request.headers.items() 
        if key.lower() not in ["host", "connection", "accept-encoding", "content-length"]
    }

    # 4. Handle based on whether the request is for streaming or not.
    if is_streaming_request:
        # --- STREAMING LOGIC ---
        backend_request = client.build_request(request.method, url, headers=headers, json=payload)
        backend_response = await client.send(backend_request, stream=True)

        async def response_generator():
            all_chunks = []
            acc_eventstrings = []
            acc_datastrings = []
            acc_loadedstrings = []
            acc_err_strings = []
            acc_text = []
            async for chunk in backend_response.aiter_raw():
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
                            acc_text.append(loaded["delta"])
                        except:
                            acc_err_strings.append(i)
                yield chunk

            # sfx = "\n\n"
            # for i in acc_loadedstrings:
            #     enc = f"data: {json.dumps(i)}{sfx}".encode()
            #     yield enc

            # for i in acc_eventstrings:
            #     enc = f"{i}{sfx}".encode()
            #     yield enc
            # yield f"data: [DONE]{sfx}".encode()
            unique_events = []
            for i in acc_eventstrings:
                if "delta" in i and i not in unique_events:
                    unique_events.append(i)
                elif "delta" not in i:
                    unique_events.append(i)
            await backend_response.aclose()

        return StreamingResponse(
            response_generator(),
            status_code=backend_response.status_code,
            headers=backend_response.headers,
        )
    else:
        # --- NON-STREAMING LOGIC ---
        backend_response = await client.request(request.method, url, headers=headers, content=payload)
        content = backend_response.content.decode()
        splits = content.split("\n")
        test_json = backend_response.json()
        return Response(
            content=backend_response.content,
            status_code=backend_response.status_code,
            headers=backend_response.headers,
        )


# --- API Endpoints ---
@app.get("/v1/models")
async def proxy_models(request: Request):
    """
    Proxies requests to the /v1/models endpoint to fetch the list of available models.
    This is a non-streaming GET request.
    """
    headers = {
        key: value for key, value in request.headers.items() 
        if key.lower() not in ["host", "connection", "accept-encoding"]
    }
    
    backend_response = await client.get("/v1/models", headers=headers)
    
    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers=backend_response.headers,
    )


@app.post("/v1/chat/completions")
async def proxy_chat(request: Request):
    """
    Proxies requests to the /v1/chat/completions endpoint of the backend.
    """
    return await proxy_post_request(request, "/v1/chat/completions")


@app.post("/v1/completions")
async def proxy_completions(request: Request):
    """
    Proxies requests to the /v1/completions endpoint of the backend.
    """
    return await proxy_post_request(request, "/v1/completions")


@app.post("/v1/responses")
async def proxy_responses(request: Request):
    """
    Proxies requests to the /v1/responses endpoint of the backend (Azure specific).
    """
    return await proxy_post_request(request, "/v1/responses")


# --- Main Entry Point ---
if __name__ == "__main__":
    import uvicorn
    # To run this application, use the command:
    # uvicorn main:app --host 0.0.0.0 --port 8000
    #
    # You can also set the BACKEND_URL environment variable, for example:
    # BACKEND_URL=https://your-custom-backend.com uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)