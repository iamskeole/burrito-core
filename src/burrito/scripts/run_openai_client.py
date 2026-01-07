from openai import OpenAI

API_KEY = "sk-mock"
BASE_URL = "http://127.0.0.1:8000/v1"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

input_str = "Write a one-sentence bedtime story about a unicorn."

# [NOTE: DONE] # like chat/completions, one of the examples in openai docs
input_completions_single = [
    {
        "role": "user",
        "content": "Say 'double bubble bath' ten times fast.",
    },
]

# [NOTE: TODO] # multiple messages / context
# doesn't crash, but doesn't append user messages
# because it looks for content to be a list of dicts
# also, i think it SHOULD crash, since it's not providing the message type per
# the default schema, but it doesn't, probably because the
# EasyInputMessageParam (i think what these map to) is a TypedDict
# with total=False (meaning it's not expected to have all keys,
# even if the base type doesn't flag it as Optional, which technically means
# required... fuck me)
input_completions_multiple = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"},
]

# [NOTE: DONE] # like codex
input_responses = [
    {
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": "Hi",
            }
        ],
    }
]

stream = client.responses.create(model="gpt-oss-20b", input=input_str, stream=False)
print(stream)

# for event in stream:
#     print("=" * 42)
#     print(event)
