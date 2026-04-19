Use this tool to execute Python code in your chain of thought. The code will not be shown to the user. This tool should be used for internal reasoning, but not for code that is intended to be visible to the user (e.g. when creating plots, tables, or files).

When you send a message containing Python code to python, it will be executed in a **STATEFUL** Jupyter notebook environment. python will respond with the output of the execution or time out after **{timeout} seconds**.

IMPORTANT: Internet access for this session is **DISABLED**. Do not try to install packages or access outside resources as these requests will fail. You must only rely on stdlib.