Use this tool to execute STATELESS Python code in your chain of thought. The code will not be shown to the user. This tool should be used for internal reasoning, but not for code that is intended to be visible to the user (e.g. when creating plots, tables, or files).

When you send a message containing python code to python, it will be executed in a **STATELESS** docker container, and the stdout of that process will be returned to you. You **MUST** use print statements to access the output.

IMPORTANT: Your python environment is **NOT** shared between calls. You will have to *pass your entire code each time*.

IMPORTANT: Internet access for this session is **DISABLED**. Do not try to install packages or access outside resources as these requests will fail. You must only rely on stdlib.