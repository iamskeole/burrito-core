from openai import OpenAI

API_KEY = "sk-mock"
BASE_URL = "http://127.0.0.1:8000/v1"
MODEL = "openai/gpt-oss-20b"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

chat = [
    {
        "role": "user",
        "content": "Say 'double bubble bath' ten times fast.",
    },
]
responses = [
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

stream_responses = client.responses.create(model=MODEL, input=responses, stream=True)
stream_chat = client.chat.completions.create(model=MODEL, messages=chat, stream=True)

acc_responses = []
for r in stream_responses:
    acc_responses.append(r)

acc_chat = []
for c in stream_chat:
    acc_chat.append(c)

x = 1