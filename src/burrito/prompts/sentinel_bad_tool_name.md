**Invalid output**: invalid or malformed tool name: `{recipient}`.

Calls to these tools must go to the analysis channel: 'python', 'browser'.
Calls to these tools must go to the commentary channel: 'functions'.
Example: <|channel|>analysis to=python <|constrain|> code<|message|>code_input.
Example: <|channel|>commentary to=functions.shell <|constrain|> json<|message|>tool_inputs.

- valid namespaces:
{valid_namespaces}
- valid tools:
{valid_tools}

**IMPORTANT**: python and browser tools also act as their own namespaces, when available. This means you must NOT include the `functions` namespace when calling python or browser, eg only `python` to execute python code or `browser.open` to visit a web page.

You are trying to call: `{recipient}`. The tool name is not part of valid tools available to you. You MUST include the correct namespace and tool name syntax in your call, eg. `to=(namespace.function_name | python | browser.action_name)`.