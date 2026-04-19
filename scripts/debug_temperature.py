import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas
from openai import Client

INPUT = "What's the 73rd fibonacci number?"
MODEL_NAME = "openai/gpt-oss-20b"
N_THREADS_PER_EVAL = 8
N_EVALS = 1
TEMPERATURE = None  # 0.0001
SEED = 69421337
REASONING_EFFORT = "low"
BASE_URL = "http://localhost:8888/v1"  # "http://apollo.local:9999/v1"  #


def run_chat_completions(stream: bool):
    client = Client(api_key="sk-none", base_url=BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": f"Current time: {time.time()}. {INPUT}"}],
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
        reasoning_content = output_object.message.model_extra["reasoning_content"]
        output_text = output_object.message.content
    return {"reasoning_content": reasoning_content, "output_text": output_text}


def run_responses(stream: bool):
    client = Client(api_key="sk-none", base_url=BASE_URL)
    response = client.responses.create(
        model=MODEL_NAME,
        input=[
            {
                "role": "user",
                "content": f"Current time: {time.time()}. {INPUT}",
            },
        ],
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
        return {"status": response.status, "usage": response.usage.model_dump()}
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
    print("example reasoning: ", results[0]["stream_0"]["chat"][0]["reasoning_content"])
    print("example output: ", results[0]["stream_0"]["chat"][0]["output_text"])
    print("=" * 42)
    for result in results:
        print("-" * 42)
        print(json.dumps(result, indent=4))
    return results


# done = test_determinism()


def test_aime_sequential(wire_api: str = "responses"):

    def normalize_number(s):
        match = re.match(r"\d+", s)  # match digits from the start
        if not match:
            return None
        return match.group(0)

    path1 = f"https://huggingface.co/datasets/opencompass/AIME2025/raw/main/aime2025-I.jsonl"
    df1 = pandas.read_json(path1, lines=True)
    path2 = f"https://huggingface.co/datasets/opencompass/AIME2025/raw/main/aime2025-II.jsonl"
    df2 = pandas.read_json(path2, lines=True)
    examples = [row.to_dict() for _, row in df1.iterrows()] + [
        row.to_dict() for _, row in df2.iterrows()
    ]
    examples = [
        {
            "question": row["question"],
            "answer": normalize_number(row["answer"])
            if isinstance(row["answer"], str)
            else row["answer"],
        }
        for row in examples
    ]

    AIME_TEMPLATE = """
    {question}
    Please reason step by step, and put your final answer within \\boxed{{}}.
    """

    for ix, row in enumerate(examples):
        print("============================")
        global INPUT
        question = row["question"]
        INPUT = AIME_TEMPLATE.format(question=question)
        print(f"[{ix}] {INPUT}")

        if wire_api == "responses":
            res = run_responses(stream=False)
            print(json.dumps(res))
        else:
            res = run_chat_completions(stream=False)
            print(json.dumps(res))


# test_aime_sequential()
test_determinism()
