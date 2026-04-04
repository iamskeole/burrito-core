import httpx
from gpt_oss.tools.python_docker.docker_tool import PythonTool
from openai_harmony import ToolNamespaceConfig

from burrito import __repo__, __version__
from burrito.common.config import settings
from burrito.common.utils import get_prompt


# subclass for future functionality
class BurritoPython(PythonTool):
    def __init__(self):
        # not THAT dangerous if it's within docker.. ?
        if "jupyter" in settings.PYTHON_BACKEND:
            backend = "dangerously_use_local_jupyter"
        else:
            backend = settings.PYTHON_BACKEND

        timeout = settings.PYTHON_EXECUTION_TIMEOUT_SECONDS
        super().__init__(execution_backend=backend, local_jupyter_timeout=timeout)

    def patch_tool_description(self, config: ToolNamespaceConfig):
        backend = self._execution_backend
        timeout = self._local_jupyter_timeout
        ua_test = f"burrito-liveness-check/{__version__}; +{__repo__}"
        headers = {"User-Agent": ua_test}
        wikipedia = httpx.get("https://www.wikipedia.org/", headers=headers)
        internet_enabled = wikipedia.status_code < 400
        suffix = "online" if internet_enabled else "offline"

        if "jupyter" in backend:
            description = get_prompt(
                f"python_tool_description_jupyter_{suffix}"
            ).format(timeout=timeout)
        else:
            description = get_prompt(f"python_tool_description_docker_{suffix}")

        config.description = description
        return config

    @property
    def tool_config(self) -> ToolNamespaceConfig:
        config = super().tool_config
        self.patch_tool_description(config)
        return config
