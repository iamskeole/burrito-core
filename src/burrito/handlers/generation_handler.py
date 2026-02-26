from typing import AsyncGenerator, Dict, List, Union

from openai.types.completion import Completion

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid
from burrito.services.inference import infer_next_token
from burrito.types.create_params import CreateParams


class AdapterGenerationHandler:
    def __init__(self):
        self.can_stream = True
        self.log_id = random_uuid()
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": self.log_id}

    async def _generator(
        self,
        prompt_token_ids: List[int],
        params: CreateParams,
        headers: Dict[str, str] = {},
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        try:
            async for completion in infer_next_token(prompt_token_ids, params, headers):
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
        params: CreateParams,
        headers: Dict[str, str] = {},
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        generator = self._generator(prompt_token_ids, params, headers)
        async for item in generator:
            yield item
