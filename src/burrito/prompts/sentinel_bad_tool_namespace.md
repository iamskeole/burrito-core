**Invalid output**: invalid or malformed namespace: `{recipient}`.

Calls to these tools must go to the analysis channel: 'python', 'browser'.
Calls to these tools must go to the commentary channel: 'functions'.
Example: <|channel|>analysis to=python <|constrain|> code<|message|>code_input.
Example: <|channel|>commentary to=functions.shell <|constrain|> json<|message|>tool_inputs.

- valid namespaces:
{valid_namespaces}
- valid tools:
{valid_tools}

You are trying to call: `{recipient}`. The namespace is not part of valid namespaces available to you. You MUST include the correct namespace and tool name syntax in your call, eg. `to=(namespace.function_name | python | browser.action_name)`.