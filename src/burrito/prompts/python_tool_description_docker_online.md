Use this tool to execute STATELESS Python code in your chain of thought. The code will not be shown to the user. This tool should be used for internal reasoning, but not for code that is intended to be visible to the user (e.g. when creating plots, tables, or files).

When you send a message containing python code to python, it will be executed in a **STATELESS** docker container, and the stdout of that process will be returned to you. You **MUST** use print statements to access the output.

IMPORTANT: Your python environment is **NOT** shared between calls. You will have to *pass your entire code each time*.

Internet access for this session is **ENABLED**.

**Rules for dependencies:**
- The environment does NOT persist between runs.
- You CANNOT rely on preinstalled non-standard-library packages.
- If your code requires external packages (not in the Python standard library), you MUST install them at runtime.

**Working with packages:**
- At the very top of the script, before importing the package, check if it is installed.
- If not installed, install it using pip via subprocess and sys.executable.
- Use this pattern:

```
import subprocess, sys
def install(package_name):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    try:
        import package_name
    except ImportError:
        install("package_name")
        import package_name
```
- Replace "package_name" with the actual package.
- Install all required external dependencies this way before using them.

**Constraints:**
- Do NOT assume any package is preinstalled except the Python standard library.
- Do NOT use shell commands like !pip install.
- Do NOT skip the installation step if a package is required.