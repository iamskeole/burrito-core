import pytest
from burrito.types.adapter.adapter_create_params_anthropic import (
    AdapterCreateParamsAnthropic,
    AdapterInputParamMessageAnthropic,
    ContentBlockText,
    ContentBlockToolUse,
    ContentBlockToolResult,
    AdapterToolParamInputAnthropic,
)
from burrito.services.harmony.harmony_service_anthropic import (
    build_message_list_anthropic,
)
from openai_harmony import Role, Author


def test_anthropic_params_validation():
    # Test valid params
    data = {
        "model": "claude-3-opus-20240229",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 1024,
    }
    params = AdapterCreateParamsAnthropic(**data)
    assert params.model == "claude-3-opus-20240229"
    assert len(params.messages) == 1
    assert params.messages[0].content == "Hello"


def test_build_message_list_anthropic_text_only():
    params = AdapterCreateParamsAnthropic(
        model="claude-3-5-sonnet-20240620",
        messages=[
            AdapterInputParamMessageAnthropic(role="user", content="Hello"),
            AdapterInputParamMessageAnthropic(role="assistant", content="Hi there"),
        ],
        max_tokens=100,
    )

    inputs = build_message_list_anthropic(params)
    assert len(inputs.messages) == 2
    assert inputs.messages[0].author.role == Role.USER
    assert inputs.messages[0].content[0].text == "Hello"
    assert inputs.messages[1].author.role == Role.ASSISTANT
    assert inputs.messages[1].content[0].text == "Hi there"


def test_build_message_list_anthropic_with_tools():
    tool = AdapterToolParamInputAnthropic(
        name="get_weather",
        description="Get weather",
        input_schema={"type": "object", "properties": {"location": {"type": "string"}}},
    )

    # Constructing params directly
    params = AdapterCreateParamsAnthropic(
        model="claude-3-5-sonnet-20240620",
        messages=[
            AdapterInputParamMessageAnthropic(role="user", content="Weather in SF?"),
            AdapterInputParamMessageAnthropic(
                role="assistant",
                content=[
                    ContentBlockText(type="text", text="Checking..."),
                    ContentBlockToolUse(
                        type="tool_use",
                        id="call_123",
                        name="get_weather",
                        input={"location": "SF"},
                    ),
                ],
            ),
            AdapterInputParamMessageAnthropic(
                role="user",
                content=[
                    ContentBlockToolResult(
                        type="tool_result", tool_use_id="call_123", content="Sunny"
                    )
                ],
            ),
        ],
        tools=[tool],
        max_tokens=100,
    )

    inputs = build_message_list_anthropic(params)

    # Check tools
    assert len(inputs.tools) == 1
    assert inputs.tools[0].name == "get_weather"

    # Check messages
    # 1. User "Weather in SF?"
    # 2. Assistant Text "Checking..."
    # 3. Assistant Tool Call (formatted)
    # 4. Tool Result (User role in Anthropic -> TOOL role in Harmony)

    msgs = inputs.messages
    assert msgs[0].author.role == Role.USER
    assert msgs[0].content[0].text == "Weather in SF?"

    assert msgs[1].author.role == Role.ASSISTANT
    assert msgs[1].content[0].text == "Checking..."

    assert msgs[2].author.role == Role.ASSISTANT
    assert msgs[2].recipient == "functions.get_weather"
    assert '"location": "SF"' in msgs[2].content[0].text

    assert msgs[3].author.role == Role.TOOL
    assert msgs[3].author.name == "functions.get_weather"  # We resolved name from ID!
    assert msgs[3].content[0].text == "Sunny"


def test_build_message_list_anthropic_system():
    params = AdapterCreateParamsAnthropic(
        model="claude",
        system="Be helpful",
        messages=[AdapterInputParamMessageAnthropic(role="user", content="Hi")],
        max_tokens=10,
    )
    inputs = build_message_list_anthropic(params)
    assert inputs.instructions == "Be helpful"
