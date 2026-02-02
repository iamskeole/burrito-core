import httpx
import re
import asyncio
from typing import Dict, Any, List

# We don't import harness or settings here to keep this file purely about 
# client-side testing logic. The calling test file handles the app reference.

def normalize(text: str) -> str:
    """Normalize whitespace and remove special characters for lenient matching."""
    if not text: return ""
    return re.sub(r"\s+", " ", text).strip().lower()

async def run_test_scenario(client, scenario: str, endpoint: str, stream: bool) -> bool:
    print(f"\n--- Test: {scenario} | Endpoint: {endpoint} | Stream: {stream} ---")
    # Ensure tool_calls is defined for all code paths
    tool_calls = []
    
    is_chat = "chat/completions" in endpoint
    is_responses = "responses" in endpoint
    
    # Defaults
    model = "gpt-4"
    messages = []
    tools = []
    
    # --- Scenario Setup ---
    if scenario == "basic":
        prompt = "Continue this sentence: `The quick brown fox`. Do not respond with anything but the continuation."
        messages = [{"role": "user", "content": prompt}]
        
    elif scenario == "native_python":
        prompt = "Calculate 2+2 using python. Do not explain, just return the result."
        messages = [{"role": "user", "content": prompt}]
        
    elif scenario == "native_browser_open":
        prompt = "Open example.com and tell me the title of the page."
        messages = [{"role": "user", "content": prompt}]
        
    elif scenario == "native_browser_search":
        prompt = "Search for 'Python programming language' on the web. Verifiy that multiple results are returned. Do not explain."
        messages = [{"role": "user", "content": prompt}]
        
    elif scenario == "function":
        prompt = "What is the stock price of AAPL?"
        messages = [{"role": "user", "content": prompt}]
        tools = [{
            "type": "function",
            "function": {
                "name": "get_stock_price",
                "description": "Get the current stock price of a company",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "The stock symbol, e.g. AAPL"}
                    },
                    "required": ["symbol"]
                }
            }
        }]
        
    elif scenario == "custom_text":
        prompt = "Use the 'text_formatter' tool to uppercase the word 'hello'."
        messages = [{"role": "user", "content": prompt}]
        
        # Schema differs for Chat vs Responses
        if is_chat:
            tools = [{
                "type": "custom",
                "custom": {
                    "name": "text_formatter",
                    "description": "Formats text",
                    "format": {"type": "text"}
                }
            }]
        else:
            tools = [{
                "type": "custom",
                "name": "text_formatter",
                "description": "Formats text",
                "format": {"type": "text"}
            }]
            
    elif scenario == "custom_grammar":
        prompt = "Use the 'grammar_tool' to generate a simple color name."
        messages = [{"role": "user", "content": prompt}]
        
        # Simple regex grammar for colors
        regex_grammar = r"(red|green|blue)"
        
        if is_chat:
            tools = [{
                "type": "custom",
                "custom": {
                    "name": "grammar_tool",
                    "description": "Generates colors",
                    "format": {
                        "type": "grammar",
                        "syntax": "regex",
                        "definition": regex_grammar
                    }
                }
            }]
        else:
            tools = [{
                "type": "custom",
                "name": "grammar_tool",
                "description": "Generates colors",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": regex_grammar
                }
            }]
            
    else:
        print(f"Unknown scenario: {scenario}")
        return False

    # --- Execution ---
    try:
        # tool_calls already initialized above
        if is_chat:
            # v1/chat/completions
            
            # The client library handles tools mapping for standard function tools,
            # but for "custom" type we typically need to pass exactly what we built.
            # OpenAI client validates `tools` strictly, so passing 'custom' type might fail validation locally
            # if we use `client.chat.completions.create`.
            # For standard Function and Native tools (python/browser are auto-handled by backend if not passed explicitly,
            # but here native tools are implicit? User said "native tool call (python)" implying we rely on backend having it enabled.
            # Scenarios 2,3,4: we don't pass `tools` array, we assume global tools are on.
            # Scenarios 5,6,7: we pass `tools` or `extra_body` for custom.
            
            kwargs = {
                "model": model,
                "messages": messages,
                "stream": stream,
            }
            if tools:
                # To bypass client validation for "custom" tools, we pass them via extra_body
                # BUT for standard function tools (Scenario 5), we can use `tools` param.
                if scenario == "function":
                    kwargs["tools"] = tools
                else:
                    # Custom tools - pass via extra_body to bypass strict client validation
                    kwargs["extra_body"] = {"tools": tools}

            response = await client.chat.completions.create(**kwargs)
            
            content = ""
            
            if stream:
                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content += delta.content
                    if delta.tool_calls:
                         # Accumulating tool calls in stream is complex, simplified check:
                         for tc in delta.tool_calls:
                             if tc.function and tc.function.name:
                                 tool_calls.append(tc.function.name)
            else:
                msg = response.choices[0].message
                content = msg.content or ""
                if msg.tool_calls:
                    tool_calls = [tc.function.name for tc in msg.tool_calls]

        elif is_responses:
            # v1/responses - Use raw http client since it's custom endpoint
            payload = {
                "model": model,
                "input": messages[0]["content"], 
                "stream": stream
            }
            if tools:
                payload["tools"] = tools

            # We use client._client (httpx client)
            # Use request(...) to support stream=True context manager if needed?
            # Actually client.stream(...) is better.
            async with client._client.stream("POST", endpoint, json=payload) as response:
            
                if stream:
                    # Processing SSE stream from raw response
                    content = ""
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            raw_data = line[len("data:"):].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                data = __import__("json").loads(raw_data)
                                # Burrito v1/responses stream format:
                                # typically yields chunks of the output object or deltas.
                                # Assuming simplified structure or standard adapter output.
                                # Let's try to extract text from common fields.
                                # Check AdapterChatCompletionChunk or similar.
                                # Usually: choices[0].delta.content or output[...].content
                                
                                # If it mimics OpenAI chunks:
                                if "choices" in data:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        content += delta["content"] or ""
                                    if "tool_calls" in delta: # if tools used
                                         for tc in delta.get("tool_calls", []):
                                             if "function" in tc and "name" in tc["function"]:
                                                 tool_calls.append(tc["function"]["name"])

                                # If it's Burrito Responses format (list of outputs):
                                elif "delta" in data:
                                    content += data["delta"]
                            except:
                                pass
                    # Fallback if parsing failed: if content is still empty but we got data, 
                    # maybe we missed the specific field. 
                    # For now, let's assume we can at least get "content" if it follows params.
                else:
                    await response.aread() # Read full body
                    data = response.json()
                    # Parse 'output' list
                    content = ""
                    # Flatten output
                    for item in data.get("output", []):
                        if item.get("type") == "message":
                            for part in item.get("content", []):
                                if part.get("type") == "output_text":
                                    content += part.get("text", "")
                                elif part.get("type") == "tool_call":
                                    tool_calls.append(part.get("name"))

        # --- Validation ---
        content_norm = normalize(content)

        if scenario == "basic":
            success = "jumps over the lazy dog" in content_norm
            # Fallback for failing streams if content is empty but tool calls present? No tool calls here.
            # If v1/responses stream content extract failed, we might check response status?
            # But we really want to verify content.
            
        elif scenario == "native_python":
            # Expect "4"
            success = "4" in content_norm
            
        elif scenario == "native_browser_open":
            # Example.com open check
            success = "example domain" in content_norm or "iana" in content_norm
            
        elif scenario == "native_browser_search":
            # Search result check
            # Relaxed check: look for citation markers OR mentions of results
            success = ("python" in content_norm and ("result" in content_norm or "found" in content_norm)) or "【" in content_norm
        
        elif scenario == "function":
            # Expect tool call 'get_stock_price'
            success = "get_stock_price" in str(tool_calls) or "get_stock_price" in content_norm
            
        elif scenario == "custom_text":
            # Expect tool use indicated somehow
            success = "text_formatter" in str(tool_calls) or "hello" in content_norm
            
        elif scenario == "custom_grammar":
            # Expect a color
            success = any(c in content_norm for c in ["red", "green", "blue"]) or "grammar_tool" in str(tool_calls)
            
        else:
            success = False

        if success:
            print(f"PASSED. Content len: {len(content)}")
        else:
            print(f"FAILED. Content: '{content_norm}' ToolCalls: {tool_calls}")
        
        return success

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
