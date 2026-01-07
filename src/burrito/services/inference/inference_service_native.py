from typing import AsyncGenerator, Dict, Union

from openai.types.completion import Completion

from burrito.types.adapter import AdapterCreateParams


async def generate_native(
    prompt_token_ids: list[int], params: AdapterCreateParams
) -> AsyncGenerator[Union[Completion, Dict], None]:
    cpl = Completion()
    yield cpl
