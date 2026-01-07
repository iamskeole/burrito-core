import os
import re
import threading
import time
from pathlib import Path

import nbformat
import uvicorn
from fastapi import FastAPI, HTTPException
from jupyter_client.blocking.client import BlockingKernelClient
from jupyter_client.manager import KernelManager
from pydantic import BaseModel

from burrito.types.sandbox import SandboxRequest

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

app = FastAPI(title="Sandbox Service")

# Module dir & sessions
MODULE_DIR = Path(__file__).parent.resolve()
SESSIONS_DIR = Path(os.environ.get("SESSIONS_DIR", MODULE_DIR / "sessions"))
TIMEOUT = int(os.environ.get("SANDBOX_TIMEOUT", 10))
KERNEL_IDLE_TIMEOUT = int(os.environ.get("KERNEL_IDLE_TIMEOUT", 3600))  # 1h

try:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    SESSIONS_DIR = Path("/tmp/sessions")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# --- Models ---
class RunRequest(BaseModel):
    session_id: str
    code: str
    replay_previous: bool = True


# --- Helper to read previous cells ---
def get_previous_cells(session_path: Path) -> list:
    notebook_path = session_path / "history.ipynb"
    if notebook_path.exists():
        nb = nbformat.read(notebook_path, as_version=4)
        return [cell.source for cell in nb.cells if cell.cell_type == "code"]
    return []


def clean_traceback(tb: str) -> str:
    # Strip ANSI colors
    tb = ANSI_RE.sub("", tb)
    # Remove Jupyter cell references like 'Cell In[25], line 1'
    tb = re.sub(r"^\s*Cell In\[\d+\], line \d+\n", "", tb, flags=re.MULTILINE)
    # Remove the caret line pointing to syntax column
    tb = re.sub(r"^\s*\^.*\n", "", tb, flags=re.MULTILINE)
    return tb.strip()


# --- Session kernel management ---
class SessionKernel:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.km = KernelManager(kernel_name="python3")
        self.km.start_kernel()
        self.kc: BlockingKernelClient = self.km.client()
        self.kc.start_channels()
        self.nb = nbformat.v4.new_notebook()
        self.last_used = time.time()

    def mark_used(self):
        self.last_used = time.time()

    def shutdown(self):
        try:
            self.kc.stop_channels()
            self.km.shutdown_kernel(now=True)
        except Exception:
            pass


_sessions: dict[str, SessionKernel] = {}


# --- Cleanup idle kernels ---
def cleanup_idle_kernels():
    while True:
        now = time.time()
        to_remove = []
        for session_id, kernel in list(_sessions.items()):
            if now - kernel.last_used > KERNEL_IDLE_TIMEOUT:
                kernel.shutdown()
                to_remove.append(session_id)
        for sid in to_remove:
            _sessions.pop(sid, None)
        time.sleep(60)


threading.Thread(target=cleanup_idle_kernels, daemon=True).start()


# --- Execute code on a kernel ---
def execute_code(kernel: SessionKernel, code: str) -> str:
    kernel.mark_used()
    kernel.nb.cells.append(nbformat.v4.new_code_cell(code))

    output_lines = []
    error_lines = []

    kernel.kc.execute(code)
    while True:
        msg = kernel.kc.get_iopub_msg(timeout=TIMEOUT)
        msg_type = msg["msg_type"]

        if msg_type == "status" and msg["content"]["execution_state"] == "idle":
            break

        # Capture stdout/stderr from kernel
        if msg_type == "stream":
            output_lines.append(msg["content"]["text"])

        # Capture rich display data
        elif msg_type in ("execute_result", "display_data"):
            data = msg["content"].get("data", {})
            if "text/plain" in data:
                output_lines.append(data["text/plain"])

        # Capture exceptions
        elif msg_type == "error":
            traceback = "\n".join(msg["content"].get("traceback", []))
            error_lines.append(traceback)

    if error_lines:
        output_lines = [clean_traceback(e) for e in error_lines]
    return "".join(output_lines)


# --- API endpoint ---
@app.post("/run")
async def run_code(req: SandboxRequest):
    session_path = SESSIONS_DIR / req.session_id
    session_path.mkdir(parents=True, exist_ok=True)
    notebook_path = session_path / "history.ipynb"

    # Get or create kernel
    if req.session_id not in _sessions:
        kernel = SessionKernel(req.session_id)
        if req.replay: # TODO: figure out replay from client (also, in client)
            for cell_code in get_previous_cells(session_path):
                execute_code(kernel, cell_code)
        _sessions[req.session_id] = kernel
    else:
        kernel = _sessions[req.session_id]

    # Execute new code
    try:
        output_text = execute_code(kernel, req.code)
    except Exception as e:
        output_text = f"FROM: Python Sandbox:\nError running python code, please try again.\n{repr(e)}"

    # Save notebook
    nbformat.write(kernel.nb, notebook_path)

    return {"ok": True, "result": output_text.strip()}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=False, log_level="debug")
