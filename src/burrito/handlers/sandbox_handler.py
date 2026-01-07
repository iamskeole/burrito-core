import time
import queue
from threading import Thread, Lock
from typing import Dict, Tuple

import nbformat
from jupyter_client.manager import KernelManager
from jupyter_client.blocking.client import BlockingKernelClient

from burrito.types.sandbox import SandboxRequest, SandboxResponse
from burrito.common.utils import clean_traceback

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid


class SandboxSessionKernel:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.km = KernelManager(kernel_name="python3")
        self.km.start_kernel()
        self.kc: BlockingKernelClient = self.km.client()
        self.kc.start_channels()
        self.kc.wait_for_ready(timeout=settings.SANDBOX_KERNEL_TIMEOUT)
        self.nb = nbformat.v4.new_notebook()
        self.last_used = time.time()

    def mark_used(self):
        self.last_used = time.time()

    def shutdown(self):
        print(f"Shutting down kernel for session: {self.session_id}")
        try:
            if self.km.is_alive():
                self.kc.stop_channels()
                self.km.shutdown_kernel(now=True)
        except Exception as e:
            print(f"Error shutting down kernel for {self.session_id}: {e}")


class SandboxSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.kernel = SandboxSessionKernel(self.session_id)

    def execute_code(self, code: str) -> Tuple[str, str]:
        timeout = settings.SANDBOX_KERNEL_TIMEOUT
        self.kernel.mark_used()
        self.kernel.nb.cells.append(nbformat.v4.new_code_cell(code))

        msg_id = self.kernel.kc.execute(
            code, store_history=True, allow_stdin=False, stop_on_error=False
        )

        out_buffer = []
        err_buffer = []

        while True:
            try:
                msg = self.kernel.kc.get_iopub_msg(timeout=timeout)
                msg_type = msg.get("msg_type", "unknown")
                content = msg.get("content", {})

                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                if msg_type == "stream":
                    text = content.get("text", "")
                    if content.get("name") == "stdout":
                        out_buffer.append(text)
                    else:
                        err_buffer.append(text)

                elif msg_type == "error":
                    traceback_data = content.get("traceback", [])
                    if traceback_data:
                        err_buffer.append("\n".join(traceback_data))
                    else:
                        ename = content.get("ename", "")
                        evalue = content.get("evalue", "")
                        err_buffer.append(f"{ename}: {evalue}".strip())

                elif msg_type in ["execute_result", "display_data"]:
                    data = content.get("data", {})
                    text = data.get("text/plain")
                    if text:
                        out_buffer.append(text if text.endswith("\n") else f"{text}\n")

                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break

            except TimeoutError:
                err_buffer.append(f"\nExecution timed out after {timeout} seconds.")
                break
            except Exception:
                # Handle queue.Empty or other exceptions if get_iopub_msg times out
                err_buffer.append(
                    f"\nKernel communication timed out after {timeout} seconds."
                )
                break

        # Drain the shell channel to capture final execution status.
        while True:
            try:
                reply = self.kernel.kc.get_shell_msg(
                    timeout=settings.SANDBOX_KERNEL_TIMEOUT
                )
            except queue.Empty as exc:
                raise TimeoutError(
                    "Timed out waiting for Jupyter kernel execution reply."
                ) from exc

            if reply.get("parent_header", {}).get("msg_id") != msg_id:
                continue

            reply_content = reply.get("content", {})
            if reply_content.get("status") == "error":
                traceback_data = reply_content.get("traceback")
                if traceback_data:
                    err_buffer.append("\n".join(traceback_data))
                else:
                    ename = reply_content.get("ename", "")
                    evalue = reply_content.get("evalue", "")
                    err_buffer.append(f"{ename}: {evalue}".strip())
            break

        out = "".join(out_buffer)
        err = "".join([clean_traceback(e) for e in err_buffer])

        if not out.strip():
            out = (
                "[WARN] No output available. Use print() to output anything to stdout to "
                "receive the output"
            )
        return out, err


class Sandbox:
    def __init__(self):
        self.sessions: Dict[str, SandboxSession] = {}
        self._lock = Lock()
        self.cleanup_thread = Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

    def _cleanup_loop(self):
        while True:
            timeout = settings.SANDBOX_KERNEL_TIMEOUT
            now = time.time()
            to_remove = []

            with self._lock:
                for session_id, session in self.sessions.items():
                    if now - session.kernel.last_used > timeout:
                        session.kernel.shutdown()
                        to_remove.append(session_id)

                for sid in to_remove:
                    self.sessions.pop(sid, None)
                    print(f"Cleaned up and removed session: {sid}")

            time.sleep(60)

    def get_or_create_session(self, session_id: str) -> SandboxSession:
        with self._lock:
            if session_id not in self.sessions:
                print(f"Creating new sandbox session: {session_id}")
                self.sessions[session_id] = SandboxSession(session_id)
            return self.sessions[session_id]

    def run(self, request: SandboxRequest) -> SandboxResponse:
        # TODO: replay should account for cells already in session kernel, somehow?
        session = self.get_or_create_session(request.session_id)

        if request.replay and request.previous:
            for prev_code in request.previous:
                session.execute_code(prev_code)

        stdout, stderr = session.execute_code(request.code)
        return SandboxResponse(stdout=stdout, stderr=stderr)

    def shutdown(self):
        print("Sandbox shutting down. Cleaning up all kernels...")
        with self._lock:
            for session_id, session in list(self.sessions.items()):
                session.kernel.shutdown()
                self.sessions.pop(session_id, None)
            self.sessions.clear()
        print("Sandbox shutdown complete.")


class SandboxHandler:
    def __init__(self):
        self.log_id = random_uuid()
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"sh_{self.log_id}"}
        self.sandbox = Sandbox()
