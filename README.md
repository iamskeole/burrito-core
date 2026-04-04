# `🌯 burrito`

!NOTE: word salad for the intro post, save readme for tech only, possibly only benchmarks and tldr.

A batteries-included inference harness for gpt-oss.

---

![burrito benchmarks](https://github.githubassets.com/assets/GitHub-Mark.png)

---

## Motivation

I first started thinking about something like this around August 2025 after taking OpenAI's gpt-oss model for a spin. I was extremely impressed by the efficiency of the MXFP4 quantization and how I was finally able to run a relatively intelligent model on full 131k context with room to spare, at crazy speeds, on a single RTX 3090 GPU. But at that time, tool calling was completely broken: llama.cpp was breaking all the time, only supported /v1/chat/completions and vLLM only supported tool calling on /v1/responses and it only worked on a blood moon if you were standing on your left foot touching your nose with your right pinky.

I also wanted to run the model on factory quantization as, although I fully appreciate what quantization unlocks for us GPU-poors, it was the first time it seemed like we can run a serious model at native specs (and in parallel for that matter, allowing me to serve more processes / users in the home).

Additionally, the gpt-oss model was trained with native tool support for python and browser, enabling it to write custom code and perform web search and retreival, none of which was enabled in any of the two inference engines, but two unlocks I saw as key to having something close to a gpt-4.* class model at home. Well, technically vLLM enabled them in a demo server but that was clunky to run on top of all other issues and defaulted to commercial API solutions for the browser, which I hated: what's the point of going local if I have to pay for browsing, with both cash and data?

So I figured I'd first do the obvious: wait a couple of weeks, see if fixes come through. Some did, in the form of updated chat templates, but none addressing the limitations and potential I had in mind. 

Around the end of September, I got tired of waiting and started building things myself. As it often happens though, life got in the way. I have since been doing gig work to keep the lights on, delivering burritos made of atoms. Coding took a back seat, often literally, in parking lots and late at night.

Here we are though, about 6 months in, delivering my first burrito made of bits.

Bon appetit!

## Relevance

I do wnat to praface this by saying I have nothing but utmost respect and love for the teams behind llama.cpp and vLLM and what they're enabling us 'locals' to achieve. At the same time, while I believe they're both doing a fantastic job at inferencing, there's a specialization issue I see starting to take shape: inference engines vs. harnesses. 

I think the former is where llama.cpp and vLLM shine (maximum speed and correctness for next token prediction), whereas something like burrito can start filling the gaps on the latter: specialized, model specific harnesses that render conversations per the trainers' intention. 

Models such as gpt-oss are extremely capable. They're trained to alternate between different 'channels' for thinking and calling tools and can even backtrack into reasoning before providing final answers. Trying to fit these dynamic patterns into jinja if clauses either doesn't always work or risks biasing the models in very subtle ways that compound when it does. We need solutions that don't fight the models.

That said, it's now March 2026 and things have improved considerably in both llama.cpp and vLLM. Here's how, and why I still think there's a place for burrito.

### llama.cpp
- implements both /v1/chat/completions and /v1/responses APIs out of the box
- implements a /v1/messages API for Anthropic compatible clients
- function calling works for user defined tools on all endpoints;
- jinja failures immediately end generation and return to caller;
- handles tool calling hallucinations via mathematical constructs (grammars that bias model responses)
- does not handle hallucinations outside tool calling (eg: conversation channel requirements)
- hacks 90%+ tool calling success by using grammars; I appreciate the engineering solution, but part of me is weary of inducing hallucinations in model responses; in a nuthell, llama.cpp hardcodes a `functions.` prefix to assistant responses, while also restricting grammar to the universe of available tool names; this can lead to perfectly named tool calls that hallucinate their args and does not allow for downstream inference harnesses to make use of the model's python and browser tools (these have their own namespaces in the model's training, eg: `python` or `browser.*` and *not* `functions.browser`, `functions.python`)
- no `python` or `browser` support, neither in allowing model to output tokens for these tools, nor running actual outputs

### vLLM
- tool calling mostly works for both /v1/chat/completions and /v1/responses APIs
- no /v1/messages API for Anthropic compatible clients
- jinja failures immediately end generation and return to caller;
- no hallucination handling
- basic `python` and `browser` support by launching a separate demo server
- commercial browser APIs that require you to spend money with and send data to third parties

### burrito

- drop-in replacement for **OpenAI** and **Anthropic** APIs; accepts standard inputs for `/v1/chat/completions`, `/v1/responses` and `/v1/messages`; returns both JSON and streamed responses (and standard wire events where applicable)
- runs next-token-prediction behind the scenes, sending /v1/completions responses to either llama.cpp or vLLM, then handles conversation rendering, tool calling, state recovery from hallucinations, production health and metrics
- handles tool calling hallucinations by treating the model as an intelligent agent: telling it where it went wrong, model is smart enough to recover on its own
- native `browser` and `python` tools the model has been trained with, that can be called and processed inside the same harness, no separate servers needing to be launched
- `browser.search` runs on local `SearXNG` instance (Brave  API optional)
- `browser.open` uses custom Playwright engine (no API fees, no third parties controlling agent browser)

### tldr;
[draft] no more 'continue' spam
[draft] see here https://github.com/ggml-org/llama.cpp/pull/18675
GPT-OSS is a different beast since it supports arbitrarily many interleaved blocks, so it doesn't fit into the scheme that I mentioned above (but its parser has been rewritten to PEG as well).

- if you need maximum, single-threaded speed, don't care about (grammar) biased model responses, are ok with occasional failures and don't care about native python or browser tools, **use llama.cpp**
- if you need native quants, parallel request processing, native python and browser tools, unbiased model responses, **use burrito** (with either of llama.cpp or vLLM as next-token-prediction backends)
- do **not** use vLLM proper as it fails in many, undocumented, sometimes silent, ways

## Dogfooding

Most of the work on burrito was done by hand (the only notable exception being the frontend to debug responses), up to the point of getting all wire apis functional. Once this was unlocked, I used the model itself to help with implementing some of the operational parts: health and metrics endpoints, custom prometheus dashboards, and even packaging up for deployment. All while testing different coding harnesses (Codex CLI, Claude Code, Pi). 

## Installation

1. clone this repo

```bash
git clone https://github.com/iamskeole/burrito && cd burrito
```

2. edit [`docker-compose.yml`](/docker-compose.yml) to configure environment variables
```bash
nano docker-compose.yml
```
> *see [`config.py`](/src/burrito/common/config.py) for a list of available options; most defaults should be sane (enough!), but make sure you configure at least `BACKEND_BASE_URL` to point burrito to your inference backend (eg. llama.cpp or vLLM)*

> *comment out / remove any / all or `prometheus`, `grafana`, `searxng`, services if you're already hosting them yourself, otherwise the compose file bundles everything together*

3. point your client to burrito and burrito to your backend

```bash
# client / caller config
# or ANTHROPIC_API_URL or other config var that defines your existing backend url
export OPENAI_BASE_URL="http://<burrito-url>"

# burrito config
export BACKEND_BASE_URL="http://llamacpp-or-vllm-backend-url>"
```

4. run with docker

```bash
docker compose up --build -d
```

#### third‑party libraries

This project depends on a minimal number of open-source libraries. All packages have permissive licenses except for the SearXNG and Grafana Docker images, which is AGPL‑3.0. Detailed license information is available in [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).