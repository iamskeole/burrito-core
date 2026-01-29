query_description = (
    "// The literal search string sent to the search engine.\n"
    "// IMPORTANT: compose from user query, using the same language user asks you in, translating from English if necessary.\n"
    "// DO NOT: use English to phrase your query unless the user's question to you is also in English."
)

source_description = (
    "Selects which type of information sources are queried.\n"
    "// Controls the kind of publishers, not the topic, language, or region.\n"
    "// IMPORTANT: Use the narrowest source that matches the user's intent."
)

language_description = (
    "The language the query is written in *and* the language the results should be returned in. ISO 639-1 format (e.g., 'en', 'fr', 'ja').\n",
    "// Controls country editions, regional ranking, and local source preference.\n"
    "// ISO 639-1 format (e.g., 'en', 'fr', 'ja').\n"
    "// IMPORTANT: Infer from user query and / or conversation context.\n",
)

locale_description = (
    "The language the query is written in and the language the results should be returned in.\n"
    "// Controls linguistic interpretation, language-specific sources, and query rewriting.\n"
    "// IETF BCP 47 format (e.g., 'en-US', 'fr-FR', 'ja-JP').\n"
    "// IMPORTANT: Infer from user location data if provided, current conversation if not."
)

time_range_description = (
    "Restricts results based on publication or indexing time.\n"
    "// Controls recency bias, not sorting or relevance scoring.\n"
    "// IMPORTANT: Use the shortest time range that satisfies the query's intent."
)
