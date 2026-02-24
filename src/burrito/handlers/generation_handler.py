from typing import AsyncGenerator, Dict, List, Union

from openai.types.completion import Completion

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid
from burrito.services.inference import generate_hosted
from burrito.types.adapter import AdapterCreateParams


class AdapterGenerationHandler:
    def __init__(self):
        self.can_stream = True
        self.log_id = random_uuid()
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"{self.log_id} | {__name__}"}

    async def _generate_native(
        self, prompt_token_ids: List[int], params: AdapterCreateParams
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        yield {"error": "Native generation is not implemented yet."}  # type: ignore

    async def _generate_hosted(
        self,
        prompt_token_ids: List[int],
        params: AdapterCreateParams,
        headers: Dict[str, str] = {},
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        try:
            async for completion in generate_hosted(
                prompt_token_ids, params, headers
            ):
                if not self.can_stream:
                    self.logger.debug(
                        "generator: breaking loop", extra=self.log_extra
                    )
                    break
                yield completion
        finally:
            self.logger.debug("generator: cleaning up", extra=self.log_extra)

    async def generate(
        self,
        prompt_token_ids: List[int],
        params: AdapterCreateParams,
        headers: Dict[str, str] = {},
    ) -> AsyncGenerator[Union[Completion, Dict, str], None]:
        # TODO: implement native
        if settings.INFERENCE_BACKEND_IS_NATIVE:
            generator = self._generate_native(prompt_token_ids, params)
        else:
            generator = self._generate_hosted(prompt_token_ids, params, headers)

        async for item in generator:
            yield item
