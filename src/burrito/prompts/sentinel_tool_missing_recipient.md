**Invalid output**: you are trying to call a tool with no recipient.

Calls to these tools must go to the analysis channel: 'python', 'browser'.
Calls to these tools must go to the commentary channel: 'functions'.
Example: <|channel|>analysis to=python <|constrain|> code<|message|>code_input.
Example: <|channel|>commentary to=functions.shell <|constrain|> json<|message|>tool_inputs.

- valid namespaces:
{valid_namespaces}
- valid tools:
{valid_tools}

You tried calling: `{recipient}`.