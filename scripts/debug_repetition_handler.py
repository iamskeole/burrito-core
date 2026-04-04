from burrito.handlers.repetition_handler import RepetitionHandler
from burrito.services.harmony import ENCODING
from burrito.types.conversation_token import ConversationToken

text = "Wait a minute.```"
alt = "WAIT A MINUTE. ```def hello():\n\tprint('world')"

sentences = []
for i in range(100):
    if i % 2 == 0:
        sentences.append(f"{text}")
    else:
        sentences.append(f"{alt}")

loop = " ".join(sentences)
loop_len = len(loop)
int_tokens = ENCODING.encode(loop)
dec_tokens = [ENCODING.decode([i]) for i in int_tokens]
brr_tokens = []
handler = RepetitionHandler()
for ix, i in enumerate(dec_tokens):
    token = ConversationToken(
        created_at=0,
        id=int_tokens[ix],
        text=i,
        index=0,
        finish_reason=None,
        is_special_token=False,
    )
    brr_tokens.append(token)
    is_repeating = handler.process_new_token(token)
    if is_repeating:
        x = 1
x = 1
