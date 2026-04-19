from typing import AsyncGenerator, Dict, List, Union

import httpx
from openai.types.completion import Completion

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.services.inference import infer_next_token
from burrito.types.wire_api_params import WireApiParams


class GenerationHandler:
    def __init__(self, log_id: str, client: httpx.AsyncClient):
        self.can_stream = True
        self.log_id = log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": self.log_id}
        self.client = client

    async def _generator(
        self,
        prompt_token_ids: List[int],
        params: WireApiParams,
        headers: Dict[str, str] = {},
        grammar: str = "",
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        try:
            async for completion in infer_next_token(
                self.client, prompt_token_ids, params, headers, grammar
            ):
                if not self.can_stream:
                    if settings.DEBUG_GENERATOR_CLEANUP:
                        self.logger.debug(
                            "generator: breaking loop", extra=self.log_extra
                        )
                    break
                yield completion
        finally:
            if settings.DEBUG_GENERATOR_CLEANUP:
                self.logger.debug("generator: cleaning up", extra=self.log_extra)

    async def generate(
        self,
        prompt_token_ids: List[int],
        params: WireApiParams,
        headers: Dict[str, str] = {},
        grammar: str = "",
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        generator = self._generator(prompt_token_ids, params, headers, grammar)
        async for item in generator:
            yield item
