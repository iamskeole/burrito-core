from gpt_oss.tools.python_docker.docker_tool import PythonTool


class BurritoPython(PythonTool):
    def __init__(self, backend: str):
        super().__init__(execution_backend=backend)
