- [done] reasoning_effort for chat completions to spec (see https://platform.openai.com/docs/api-reference/chat/create, currently having it the same as /v1/responses which is wrong?)

- [done, i think] function / custom tools for completions, both input format and figuring out whether custom tools are supported? chat completion chunk object only appears to support function tools, not custom, per the api spec, but the input to create a chat completion accepts custom too, so that's confusing

- tool formatting (custom only? eg text vs grammar)
-- done for chat, responses throws an error for custom
  File "/Users/bogdandragomir/Code/burrito/burrito-core/src/burrito/plugins/responses/tool_plugin.py", line 166, in handle_on_enter_state
    output_item = self.build_output_item(tool.name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/bogdandragomir/Code/burrito/burrito-core/src/burrito/plugins/responses/tool_plugin.py", line 101, in build_output_item
    raise ValueError(f"Unknown tool type: {tool.type}")
ValueError: Unknown tool type: custom

- structured outputs? figure out how openai does it, how is the schema enforced
- figure out whether codex does NOT support NON-streams or if that's a mebug

- figure out why codex does this weird stuff in /v1/chat/completions; i.e. codex bug or mebug?

› tell me a joke


• Why don't programmers like nature? Because it has too many bugs!

• Why

• don't

• programmers

• like

• nature

• ?

• Because

• it

• has

• too

• many

• bugs

• !
