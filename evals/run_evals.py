import os

from gpt_oss.evals import aime_eval
from gpt_oss.evals.responses_sampler import ResponsesSampler

os.environ["OPENAI_API_KEY"] = "sk-none"

eval = aime_eval.AIME25Eval(n_repeats=1, num_examples=1, n_threads=1)
eval(sampler=ResponsesSampler(
    model="openai/gpt-oss-20b",
    reasoning_effort="low",
    reasoning_model=True
))