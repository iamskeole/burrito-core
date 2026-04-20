import asyncio
import contextlib
from typing import Optional

import docker
from jupyter_client.asynchronous.client import AsyncKernelClient
from jupyter_client.manager import KernelManager

from burrito.common.logger import FastAPILogger
from burrito.common.utils import random_uuid
from burrito.handlers.kernel_handler import DockerKernelManager


class AsyncJupyterSession:
    """
    Base class for Jupyter sessions. Handles the ZMQ communication
    and execution loop, regardless of where the kernel is hosted.
    """

    def __init__(self, log_id: str, timeout: float = 120.0) -> None:
        self._default_timeout = timeout
        self._client: AsyncKernelClient = AsyncKernelClient()
        self._channels_started = False
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = log_id
        self.log_extra = {"log_id": self.log_id}

    def ensure_started(self):
        if not self._channels_started:
            self._client.start_channels()
            self._channels_started = True

    async def execute(self, code: str, *, timeout: Optional[float] = None) -> str:
        self.ensure_started()
        client = self._client
        effective_timeout = timeout or self._default_timeout

        msg_id = client.execute(
            code, store_history=True, allow_stdin=False, stop_on_error=False
        )
        stdout_parts, stderr_parts = [], []

        try:
            while True:
                msg = await asyncio.wait_for(
                    client.get_iopub_msg(), timeout=effective_timeout
                )
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                msg_type, content = msg.get("msg_type"), msg.get("content", {})
                if msg_type == "stream":
                    text = content.get("text", "")
                    if content.get("name") == "stdout":
                        stdout_parts.append(text)
                    else:
                        stderr_parts.append(text)
                elif msg_type == "error":
                    traceback = content.get("traceback")
                    stderr_parts.append(
                        "\n".join(traceback)
                        if traceback
                        else f"{content.get('ename')}: {content.get('evalue')}"
                    )
                elif msg_type in {"execute_result", "display_data"}:
                    text = content.get("data", {}).get("text/plain")
                    if text:
                        stdout_parts.append(
                            text if text.endswith("\n") else f"{text}\n"
                        )
                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break

            while True:
                reply = await asyncio.wait_for(
                    client.get_shell_msg(), timeout=effective_timeout
                )
                if reply.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                reply_content = reply.get("content", {})
                if reply_content.get("status") == "error":
                    traceback = reply_content.get("traceback")
                    stderr_parts.append(
                        "\n".join(traceback)
                        if traceback
                        else f"{reply_content.get('ename')}: {reply_content.get('evalue')}"
                    )
                break
        except asyncio.TimeoutError:
            raise TimeoutError("Timed out waiting for Jupyter kernel output.")

        stdout, stderr = "".join(stdout_parts), "".join(stderr_parts)
        if stderr:
            stdout = f"{stdout.rstrip()}\n{stderr}" if stdout else stderr
        return stdout if stdout.strip() else "[WARN] No output available. Use print()."

    def _hard_close_zmq(self):
        """Kills the 'Dummy' threads by force-closing sockets."""
        with contextlib.suppress(Exception):
            self._client.stop_channels()
        for attr in ["_shell_channel", "_iopub_channel", "_stdin_channel"]:
            channel = getattr(self._client, attr, None)
            if channel and hasattr(channel, "close"):
                with contextlib.suppress(Exception):
                    channel.close()
        self._channels_started = False

    async def interrupt(self) -> None:
        """Base method to be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement interrupt()")

    def close(self) -> None:
        """Base method to be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement close()")


class InProcessJupyterSession(AsyncJupyterSession):
    def __init__(self, log_id: str, timeout: float = 120.0) -> None:
        super().__init__(log_id, timeout)
        self._km = KernelManager()
        self._km.start_kernel()
        self._client.load_connection_file(self._km.connection_file)
        self._owns_kernel = True

    async def interrupt(self) -> None:
        """
        Overridden to be async to match base class return type.
        """
        try:
            # interrupt_kernel is sync, but we wrap it in an async method
            self._km.interrupt_kernel()
        except Exception as e:
            self.logger.warning(f"Interrupt failed: {e}", extra=self.log_extra)

    def close(self) -> None:
        self._hard_close_zmq()
        if hasattr(self, "_owns_kernel") and self._owns_kernel and self._km:
            with contextlib.suppress(Exception):
                self._km.shutdown_kernel(now=True)


class ContainerJupyterSession(AsyncJupyterSession):
    def __init__(
        self,
        log_id: str,
        kernel_id: str,
        conn_info: str,
        kernel_manager: Optional[DockerKernelManager] = None,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(log_id, timeout)
        self.kernel_id = kernel_id
        self.conn_info = conn_info
        self.kernel_manager = kernel_manager
        self._connect_to_kernel()

    def _connect_to_kernel(self):
        import json
        import os
        import tempfile

        conn_dict = json.loads(self.conn_info)
        conn_dict["ip"] = f"burrito-kernel-{self.kernel_id}"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            json.dump(conn_dict, f)
            tmp_path = f.name

        self._client.load_connection_file(tmp_path)
        os.remove(tmp_path)

    async def interrupt(self) -> None:
        try:
            if self.kernel_manager is not None:
                await self.kernel_manager.release_kernel(self.kernel_id, destroy=True)
            else:
                client = docker.from_env()
                container = client.containers.get(f"burrito-kernel-{self.kernel_id}")
                # Sends POSIX SIGINT directly to the kernel to rip it out of infinite loops
                container.kill(signal="SIGINT")
        except Exception:
            try:
                # Fallback to the Jupyter Control Channel (must bypass the locked shell channel)
                channel = getattr(
                    self._client,
                    "control_channel",
                    getattr(self._client, "_control_channel", None),
                )
                if channel:
                    await channel.send(
                        {
                            "header": {"msg_id": random_uuid(), "version": "5.3"},
                            "parent_header": {},
                            "metadata": {},
                            "content": {},
                            "msg_type": "interrupt_request",
                        }
                    )
            except Exception:
                pass

    def close(self) -> None:
        self._hard_close_zmq()
