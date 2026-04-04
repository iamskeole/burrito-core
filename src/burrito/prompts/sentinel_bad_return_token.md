**Invalid output**: bad return token: `{token}`.

- messages to the user must be issued on the `final` channel and end in a `<|return|>` token.
- calls to tools or functions must be issued on one of `analysis` or `commentary` channels, include a namespace and / or recipient (e.g.: `functions.shell`, `browser.open`, `python`, etc.) and end in a special `call` token.
- transitional messages, if any, (eg.: from analysis to commentary) must end in a special `<|end|>` token.

You are trying to output the token `{token}` on the channel `{channel}`.