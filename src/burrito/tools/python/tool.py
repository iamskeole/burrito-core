from gpt_oss.tools.python_docker.docker_tool import PythonTool

from burrito.common.config import settings


class BurritoPython(PythonTool):
    def __init__(self):
        backend = settings.PYTHON_BACKEND
        super().__init__(execution_backend=backend)
