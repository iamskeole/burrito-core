from concurrent.futures import ThreadPoolExecutor

from openai import Client

INPUT = "respond with exactly 7 random words"  # "What's the 73rd fibonacci number?"
MODEL_NAME = "openai/gpt-oss-20b"
N_THREADS_PER_EVAL = 1
N_EVALS = 4
TEMPERATURE = 0.0  # 0.0001
SEED = None  # 69421337
REASONING_EFFORT = "low"
BASE_URL = "http://localhost:9999/v1"  # "http://apollo.local:9999/v1"  #


def run_chat_completions(stream: bool):
    client = Client(api_key="sk-none", base_url=BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": INPUT}],
        reasoning_effort=REASONING_EFFORT,
        temperature=TEMPERATURE,
        stream=stream,
        seed=SEED,
    )
    if stream:
        reasoning_content = ""
        output_text = ""
        for event in response:
            delta = event.choices[0].delta.model_dump()
            inc_reasoning = delta.get("reasoning_content")
            inc_output = event.choices[0].delta.content
            if inc_reasoning:
                reasoning_content += inc_reasoning
            if inc_output:
                output_text += inc_output
    else:
        output_object = response.choices[0]
        reasoning_content = output_object.message.reasoning
        output_text = output_object.message.content
    return {"reasoning_content": reasoning_content, "output_text": output_text}


def run_responses(stream: bool):
    client = Client(api_key="sk-none", base_url=BASE_URL)
    response = client.responses.create(
        model=MODEL_NAME,
        input=[{"role": "user", "content": INPUT}],
        reasoning={"effort": REASONING_EFFORT},
        temperature=TEMPERATURE,
        stream=stream,
        extra_body={"seed": SEED},
    )
    if stream:
        reasoning_content = ""
        output_text = ""
        for event in response:
            if event.type == "response.reasoning_text.delta":
                reasoning_content += event.delta
            if event.type == "response.output_text.delta":
                output_text += event.delta
    else:
        output_object = response.output  # type-ignore
        reasoning_content = output_object[0].content[0].text
        output_text = output_object[1].content[0].text

    return {"reasoning_content": reasoning_content, "output_text": output_text}


def execute_pool(stream, fn):
    with ThreadPoolExecutor(max_workers=N_THREADS_PER_EVAL) as executor:
        futures = [executor.submit(fn, (stream)) for _ in range(N_THREADS_PER_EVAL)]
        return [f.result() for f in futures]


def all_equal(items):
    return all(x == items[0] for x in items)


def test_determinism():
    results = []
    print("Collecting data...")
    for i in range(N_EVALS):
        ix = str(i + 1).zfill(2)
        result = {
            "stream_0": {
                "chat": execute_pool(stream=False, fn=run_chat_completions),
                "responses": execute_pool(stream=False, fn=run_responses),
            },
            "stream_1": {
                "chat": execute_pool(stream=True, fn=run_chat_completions),
                "responses": execute_pool(stream=True, fn=run_responses),
            },
        }
        cs0 = "✅" if all_equal(result["stream_0"]["chat"]) else "❌"
        cs1 = "✅" if all_equal(result["stream_1"]["chat"]) else "❌"
        rs0 = "✅" if all_equal(result["stream_0"]["responses"]) else "❌"
        rs1 = "✅" if all_equal(result["stream_1"]["responses"]) else "❌"
        print(f"RUN# {ix}: cc-s0 {cs0} cc-s1 {cs1} rs-s0 {rs0} rs-s1 {rs1}")
        results.append(result)
    _all = "✅" if all_equal(results) else "❌"
    print(f"ALL: {_all}")
    return results


test_determinism()
