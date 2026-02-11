import httpx
import re
import json
import asyncio
from typing import Dict, Any, List

from burrito.common.config import settings

def normalize(text: str) -> str:
    """Normalize whitespace and remove special characters for lenient matching."""
    if not text: return ""
    return re.sub(r"\s+", " ", text).strip().lower()

async def run_anthropic_test_scenario(client: httpx.AsyncClient, scenario: str, stream: bool) -> bool:
    print(f"\n--- Anthropic Test: {scenario} | Stream: {stream} ---")
    
    endpoint = "/v1/messages"
    model = settings.DEFAULT_MODEL_NAME
    messages = []
    system = None
    tools = []
    
    if scenario == "basic":
        messages = [{"role": "user", "content": "Continue this sentence: `The quick brown fox`. Do not respond with anything but the continuation."}]
    elif scenario == "system_prompt":
        system = "You are a helpful assistant that only speaks in French."
        messages = [{"role": "user", "content": "Hello, how are you?"}]
    else:
        print(f"Unknown scenario: {scenario}")
        return False

    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": messages,
        "stream": stream
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools

    try:
        content = ""
        stop_reason = None
        
        if stream:
            async with client.stream("POST", endpoint, json=payload) as response:
                if response.status_code != 200:
                    print(f"Error Status: {response.status_code}")
                    print(f"Error Detail: {await response.aread()}")
                    return False
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            evt_type = data.get("type")
                            if evt_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    content += delta.get("text", "")
                            elif evt_type == "message_delta":
                                stop_reason = data.get("delta", {}).get("stop_reason")
                        except json.JSONDecodeError:
                            pass
        else:
            response = await client.post(endpoint, json=payload)
            if response.status_code != 200:
                print(f"Error Status: {response.status_code}")
                print(f"Error Detail: {response.text}")
                return False
            
            data = response.json()
            # Anthropic non-streaming response format
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
            stop_reason = data.get("stop_reason")

        # Validation
        content_norm = normalize(content)
        print(f"Content: {content}")
        print(f"Stop Reason: {stop_reason}")

        if scenario == "basic":
            success = "jumps over the lazy dog" in content_norm
        elif scenario == "system_prompt":
            # Check for some French common words
            success = any(word in content_norm for word in ["bonjour", "ça va", "bien", "merci"])
        else:
            success = False

        if success:
            print(f"PASSED.")
        else:
            print(f"FAILED. Content: '{content_norm}'")
        
        return success

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
