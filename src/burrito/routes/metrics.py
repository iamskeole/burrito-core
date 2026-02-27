from fastapi import APIRouter, Depends, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    Summary,
    generate_latest,
)

from burrito.common.dependencies import allow_metrics_ip, require_metrics_token

router = APIRouter()

# Counters and histograms for Prometheus
request_counter = Counter(
    name="burrito_requests_total",
    documentation="Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)
# Request latency – split into success and error
request_latency_success = Histogram(
    name="burrito_request_latency_seconds_success",
    documentation="Request latency for successful HTTP responses (2xx)",
    labelnames=["method", "endpoint"],
)
request_latency_error = Histogram(
    name="burrito_request_latency_seconds_error",
    documentation="Request latency for error HTTP responses (non-2xx)",
    labelnames=["method", "endpoint"],
)

# Generation metrics – track token counts and duration per model
generation_duration_seconds = Histogram(
    name="burrito_generation_duration_seconds",
    documentation="Generation time (seconds) per model (total)",
    labelnames=["wire_api", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
generation_duration_seconds_prompt = Histogram(
    name="burrito_generation_duration_seconds_prompt",
    documentation="Generation time (seconds) per model (prompt)",
    labelnames=["wire_api", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
generation_duration_seconds_eval = Histogram(
    name="burrito_generation_duration_seconds_eval",
    documentation="Generation time (seconds) per model (eval)",
    labelnames=["wire_api", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
generation_tps_prompt = Summary(
    name="burrito_generation_tps_prompt",
    documentation="Generation tokens/s (prompt)",
    labelnames=["wire_api", "model"],
)
generation_tps_eval = Summary(
    name="burrito_generation_tps_eval",
    documentation="Generation tokens/s (eval)",
    labelnames=["wire_api", "model"],
)

# Token type counters per model
generation_input_tokens = Counter(
    name="burrito_generation_input_tokens",
    documentation="Input tokens (prompt) per model",
    labelnames=["wire_api", "model"],
)
generation_output_tokens = Counter(
    name="burrito_generation_output_tokens",
    documentation="Output tokens per model",
    labelnames=["wire_api", "model"],
)
generation_reasoning_tokens = Counter(
    name="burrito_generation_reasoning_tokens",
    documentation="Reasoning tokens per model",
    labelnames=["wire_api", "model"],
)
generation_tool_call_tokens = Counter(
    name="burrito_generation_tool_call_tokens",
    documentation="Tool call tokens",
    labelnames=["wire_api", "model", "tool_name"],
)
generation_total_tokens = Counter(
    name="burrito_generation_total_tokens",
    documentation="Total tokens generated per model",
    labelnames=["wire_api", "model"],
)
generation_tool_calls = Counter(
    name="burrito_generation_tool_calls_total",
    documentation="Tool calls",
    labelnames=["wire_api", "model", "tool_name"],
)


generation_requests_total = Counter(
    name="burrito_generation_requests_total",
    documentation="Total LLM generation requests",
    labelnames=["wire_api", "model"],
)
generation_errors_total = Counter(
    name="burrito_generation_errors_total",
    documentation="Total LLM generation errors",
    labelnames=["wire_api", "model"],
)


@router.get(
    "/metrics", dependencies=[Depends(require_metrics_token), Depends(allow_metrics_ip)]
)
async def prometheus_metrics(request: Request) -> Response:
    """Return Prometheus metrics for scraping.

    The metrics are generated on the fly using the counters/histograms
    defined above.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
