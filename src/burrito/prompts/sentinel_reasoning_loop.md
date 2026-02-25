**Invalid output**: you seem to be stuck in a reasoning loop inside the analysis channel. Try to break out of it by outputting a final message or a tool call.

Valid channels: analysis, commentary, final.
Channel must be included for every message.
Calls to these tools must go to the analysis channel: 'python', 'browser'.
Calls to these tools must go to the commentary channel: 'functions'.