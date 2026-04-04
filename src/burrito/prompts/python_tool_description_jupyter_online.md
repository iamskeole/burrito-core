Use this tool to execute Python code in your chain of thought. The code will not be shown to the user. This tool should be used for internal reasoning, but not for code that is intended to be visible to the user (e.g. when creating plots, tables, or files).

When you send a message containing Python code to python, it will be executed in a **STATEFUL** Jupyter notebook environment. python will respond with the output of the execution or time out after {timeout} seconds.

Internet access for this session is **ENABLED**.

**Rules for dependencies:**
- You MAY install external (non-standard-library) Python packages.
- You SHOULD use notebook-compatible installation commands.

**Working with packages**:
- If a package is not part of the Python standard library, install it using:

  `%pip install package_name`

- Place the installation in a separate cell before importing the package.
- After installation, import the package normally.
- Use this pattern:

```
%pip install requests
import requests
```

**Constraints:**

- Prefer %pip install over !pip install to ensure the correct Python environment is used.
- Do NOT use subprocess or sys.executable unless explicitly necessary.
- Assume the environment persists within the notebook session.
