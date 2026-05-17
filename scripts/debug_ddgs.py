from ddgs import DDGS

url = "https://www.reuters.com/world/china/trump-xi-set-second-day-talks-after-taiwan-warning-2026-05-14/"
url = "https://platform.claude.com/docs/en/api/messages"
# result = DDGS().extract(
#     url,
# )
#
result = DDGS().news("trump visit china", region="en-en")
print(result)

# searxng may be a bit better for search?
# but this would be just a pip install
# also, seems ddgs can resolve reuters?! maybe add as fallback then?
