from gpt_oss.tools.python_docker.docker_tool import PythonTool

from burrito.common.config import settings


class BurritoPython(PythonTool):
    def __init__(self):
        backend = settings.PYTHON_BACKEND or "dangerously_use_local_jupyter"
        super().__init__(execution_backend=backend)
