from typing import AsyncGenerator, Dict, Union

from openai.types.completion import Completion

from burrito.types.adapter import AdapterCreateParams


# TODO: decide whether native, in-process inference makes sense
# probably going full hosted
async def generate_native(
    prompt_token_ids: list[int], params: AdapterCreateParams
) -> AsyncGenerator[Union[Completion, Dict], None]:
    yield {}
