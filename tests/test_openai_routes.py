import pytest
import httpx
from openai import AsyncOpenAI
import sys
import os

# Ensure we can import from sibling file
sys.path.append(os.path.dirname(__file__))

from debug_openai_routes import run_test_scenario
from burrito.main import app as harness_app
from burrito.common.config import settings

# Enable tools for E2E tests
settings.IS_PYTHON_TOOL_ENABLED = True
settings.IS_BROWSER_TOOL_ENABLED = True

@pytest.fixture
def openai_client_e2e():
    """
    Fixture that provides an AsyncOpenAI client connected to the harness app.
    The harness app is configured to hit the REAL backend defined in env vars.
    """
    client = AsyncOpenAI(
        api_key="fake-key",
        base_url="http://testserver/v1",
        http_client=httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness_app),
            base_url="http://testserver"
        )
    )
    yield client

SCENARIOS = [
    # "basic",
    # "function",
    # "native_python",
    "native_browser_open",
    # "native_browser_search",
    # "custom_text",
    # "custom_grammar"
]

ENDPOINTS = [
    # "/v1/chat/completions",
    "/v1/responses"
]

STREAMS = [
    True,
    False
]

@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("stream", STREAMS)
async def test_e2e_scenario(openai_client_e2e, scenario, endpoint, stream):
    success = await run_test_scenario(openai_client_e2e, scenario, endpoint, stream)
    assert success, f"Failed: {scenario} | {endpoint} | Stream={stream}"

# PYTHONPATH=src uv run -m pytest -vv