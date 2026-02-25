**Invalid output**: bad return token: `{token}`.

- user messages must be issued on the 'final' channel and end in a <|return|> token.
- calls to tools or functions must be issued on one of 'analysis' or 'commentary' channels, include a namespace and recipient (e.g.: functions.shell) and end in a special <|call|> token.
- transitional messages, if any, (eg.: analysis to commentary) must end in a special <|end|> token.

You are trying to output the token `{token}` on the channel `{channel}`.