from gpt_oss.tools.python_docker.docker_tool import PythonTool

from burrito.handlers.generation_handler import AdapterGenerationHandler
from burrito.tools.browser.tool import BurritoBrowser

from burrito.common.config import settings

python_backend = "docker"  # "dangerously_use_local_jupyter" #settings.PYTHON_BACKEND

generation_handler_singleton = AdapterGenerationHandler()
python_tool_singleton = PythonTool(execution_backend=python_backend)
browser_tool_singleton = BurritoBrowser()


def get_generation_handler() -> AdapterGenerationHandler:
    return generation_handler_singleton


def get_python_tool() -> PythonTool:
    return python_tool_singleton


def get_browser_tool() -> BurritoBrowser:
    return browser_tool_singleton
