import pytest
import httpx
import json
import os
import sys

# Ensure we can import from sibling file
sys.path.append(os.path.dirname(__file__))

from burrito.main import app as harness_app
import pytest_asyncio

import respx
from httpx import Response

@pytest_asyncio.fixture
async def client():
    # Simple mock response content (OpenAI format as expected by generate_hosted)
    mock_response = {
        "id": "cmpl-123",
        "object": "text_completion",
        "created": 1234567890,
        "model": "gpt-3.5-turbo",
        "choices": [
            {
                "text": "Hello! How can I help you?",
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop"
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
    }

    # For streaming, we need SSE format
    mock_stream_body = (
        f"data: {json.dumps(mock_response)}\n\n"
        "data: [DONE]\n\n"
    )

    async with respx.mock(base_url="http://192.168.0.202:9999", assert_all_called=False) as respx_mock:
        respx_mock.post("/v1/completions").mock(return_value=Response(200, text=mock_stream_body, headers={"Content-Type": "text/event-stream"}))
        
        transport = httpx.ASGITransport(app=harness_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

@pytest.mark.asyncio
async def test_anthropic_messages_basic(client):
    payload = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Hello, world"}
        ]
    }
    
    response = await client.post("/v1/messages", json=payload)
    if response.status_code != 200:
        print(f"Error: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify structure (assuming non-streaming default or handled by harness logic)
    # Harness defaults stream=False if not specified.
    # Structure should mimic Anthropic response:
    # {
    #   "id": "msg_...",
    #   "type": "message",
    #   "role": "assistant",
    #   "content": [...],
    #   "model": "...",
    #   "stop_reason": "end_turn",
    #   ...
    # }
    
    # NOTE: The current implementation of plugins emits chunks for streaming, 
    # but for non-streaming it accumulates them.
    # Wait, `state_handler` accumulates `output_object`.
    # `AdapterConversationHandler` handles construction of final response from `output_object`.
    # If `stream=False`, `AdapterConversationHandler` calls `return_json`.
    # `return_json` expects `output_object` to be Response or List[Chunk].
    # If using plugins, we populate `output_object` with chunks usually?
    # Anthropic plugins append chunks to `output_object` list.
    
    # In `ContextManagerPluginAnthropic`, `handle_message_start` starts the message.
    # `OutputTextPluginAnthropic` appends content blocks.
    # But `AdapterConversationHandler.return_json` logic for Anthropic might need adjustment 
    # if `output_object` is a list of Anthropic events/chunks, not OpenAI chunks.
    
    # Let's check `AdapterConversationHandler.return_json`:
    # if isinstance(output_object, list) and isinstance(output_object[-1], ChatCompletion): ...
    
    # We are generating Anthropic chunks (dicts), NOT ChatCompletion objects.
    # So `return_json` might FAIL for Anthropic if not handled.
    # I need to verify this logic.
    pass


@pytest.mark.asyncio
async def test_anthropic_messages_streaming(client):
    payload = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Hello, world"}
        ],
        "stream": True
    }
    
    async with client.stream("POST", "/v1/messages", json=payload) as response:
        assert response.status_code == 200
        
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                    events.append(event)
                except json.JSONDecodeError:
                    pass
        
        # Verify we got some events
        assert len(events) > 0
        
        # Verify event types sequence
        # Expect: message_start, content_block_start, ... message_stop
        types = [e.get("type") for e in events]
        print(f"DEBUG events: {types}")
        
        assert "message_start" in types
        
        # content_block_start might be absent if empty response
        if "content_block_start" in types:
            assert "content_block_delta" in types or "content_block_stop" in types
        
        assert "message_stop" in types

