#### TODO

[x] [plugins/responses/tool_input.py](/src/burrito/plugins/responses/tool_input.py#L74)
+ refactor responses to match chat implementations (tool registry)

[x] [plugins/responses/native_tool_call.py](/src/burrito/plugins/responses/native_tool_call.py)
+ implement web search and code interpreter
+ do it properly, figure out a way to only call done event once successful
+ figure out if it can be replicated for chat (likely no)

[x] [services/harmony/harmony_service_chat](/src/burrito/services/harmony/harmony_service_chat.py#L33)
+ prune reasoning: something still off with chat, responses ok
