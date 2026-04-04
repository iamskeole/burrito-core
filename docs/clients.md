# Client Configuration

The following examples illustrate how to make each of the three supported API clients operate in **agentic mode** – they expose tool‑call and/or function‑call capabilities so that burrito can dispatch model interactions as required.

## OpenAI Codex
`.codex/config.toml`

```
model = "openai/gpt-oss-20b"
model_provider = "local"
model_reasoning_effort = "high"
model_context_window = 131072
hide_agent_reasoning = false
show_raw_agent_reasoning = true

[model_providers.burrito]
name = "burrito"
api_key = "sk_none"
base_url = "http://127.0.0.1:8000/v1"
wire_api = "responses"

[profiles.burrito]
name = "burrito"
model_provider = "burrito"

[features]
web_search_request = true
```
> cli does NOT show agent reasoning irrespective of settings here, but leaving for posterity and in the event OpenAI decides to show reasoning in the tui

## Claude Code 
`.claude/settings.json`

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8000",
    "ANTHROPIC_API_KEY": "sk-none",
    "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENABLE_TELEMETRY": "0",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
    "CLAUDE_CODE_EFFORT_LEVEL": "high",
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
    "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION": false,
    "CLAUDE_CODE_SUBAGENT_MODEL": "openai/gpt-oss-20b",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "openai/gpt-oss-20b",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "openai/gpt-oss-20b",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "openai/gpt-oss-20b",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "openai/gpt-oss-20b"
  },
  "model": "openai/gpt-oss-20b"
}
```
> do NOT include the /v1 suffix in `ANTHROPIC_BASE_URL`, CC does it itself

## Pi
`.pi/agent/models.json`

```json
{
  "providers": {
    "burrito": {
      "baseUrl": "http://127.0.0.1:8000/v1",
      "apiKey": "sk-none",
      "api": "openai-completions",
      "models": [
        {
          "id": "openai/gpt-oss-20b",
          "name": "OpenAI gpt-oss 20B",
          "reasoning": true,
          "input": ["text"],
          "contextWindow": 131072,
          "maxTokens": 131072,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
        }
      ]
    }
  }
}
```
> maxTokens seems to default to 32000 irrespective of config value set here
> pi should work with any wire api, just change the `api` key above to ('openai-completions' | 'openai-responses' | 'anthropic-messages'); of the three, only openai-completions shows raw reasoning traces in the tui