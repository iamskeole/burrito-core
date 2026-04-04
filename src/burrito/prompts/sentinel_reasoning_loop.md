**Invalid output**: you are stuck in a reasoning loop inside the 'analysis' channel. You must output either a tool call on the 'commentary' channel, or an output message to the user on the 'final' channel.

Valid channels: analysis, commentary, final.
Channel must be included for every message.
Calls to these tools must go to the analysis channel: 'python', 'browser'.
Calls to these tools must go to the commentary channel: 'functions'.