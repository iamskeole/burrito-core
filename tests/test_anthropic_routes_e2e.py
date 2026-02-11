import pytest
import httpx
import sys
import os

# Ensure we can import from sibling file
sys.path.append(os.path.dirname(__file__))

from debug_anthropic_routes import run_anthropic_test_scenario
from burrito.main import app as harness_app
from burrito.common.config import settings

# Enable tools for E2E tests if we decide to add tool scenarios
settings.IS_PYTHON_TOOL_ENABLED = True
settings.IS_BROWSER_TOOL_ENABLED = True

@pytest.fixture
def anthropic_client_e2e():
    """
    Fixture that provides an httpx client connected to the harness app.
    Exactly like OpenAI E2E but for Anthropic routes.
    """
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness_app),
        base_url="http://testserver"
    )
    yield client

SCENARIOS = [
    "basic",
    "system_prompt"
]

STREAMS = [
    True,
    False
]

@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("stream", STREAMS)
async def test_anthropic_e2e_scenario(anthropic_client_e2e, scenario, stream):
    success = await run_anthropic_test_scenario(anthropic_client_e2e, scenario, stream)
    assert success, f"Failed Anthropic E2E: {scenario} | Stream={stream}"
