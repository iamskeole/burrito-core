import asyncio
from typing import AsyncIterator, Optional

import httpx
from gpt_oss.tools.python_docker.docker_tool import PythonTool
from openai_harmony import Message, TextContent, ToolNamespaceConfig

from burrito import __repo__, __version__
from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import get_prompt, random_uuid
from burrito.handlers.kernel_handler import DockerKernelManager
from burrito.tools.python.async_jupyter_session import (
    AsyncJupyterSession,
    ContainerJupyterSession,
    InProcessJupyterSession,
)


class BurritoPython(PythonTool):
    # override the type hint of the base class attribute to avoid pylance moaning
    _jupyter_session: Optional[AsyncJupyterSession]

    def __init__(
        self,
        log_id: str = "",
        is_placeholder: bool = False,
        kernel_id: Optional[str] = None,
        conn_info: Optional[str] = None,
        kernel_manager: Optional[DockerKernelManager] = None,
    ):
        backend = settings.PYTHON_BACKEND
        timeout = settings.PYTHON_EXECUTION_TIMEOUT_SECONDS

        self._execution_backend = backend
        self._local_jupyter_connection_file = None
        self._local_jupyter_timeout = timeout
        self.kernel_id = kernel_id  # Store the ID passed from SessionHandler
        self.conn_info = conn_info
        self.kernel_manager = kernel_manager

        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = log_id or random_uuid()
        self.log_extra = {"log_id": self.log_id}

        self._execution_lock = asyncio.Lock()
        self._jupyter_session = None

    def patch_tool_description(self, config: ToolNamespaceConfig):
        backend = self._execution_backend
        timeout = self._local_jupyter_timeout
        ua_test = f"burrito-liveness-check/{__version__}; +{__repo__}"
        headers = {"User-Agent": ua_test}
        try:
            wikipedia = httpx.get(
                "https://www.wikipedia.org/", headers=headers, timeout=5.0
            )
            internet_enabled = wikipedia.status_code < 400
        except Exception:
            internet_enabled = False

        suffix = "online" if internet_enabled else "offline"
        if "jupyter" in backend:
            description = get_prompt(
                f"python_tool_description_jupyter_{suffix}"
            ).format(timeout=timeout)
        else:
            description = get_prompt(f"python_tool_description_docker_{suffix}")

        config.description = description
        return config

    @property
    def tool_config(self) -> ToolNamespaceConfig:
        config = super().tool_config
        self.patch_tool_description(config)
        return config

    async def _resolve_jupyter_session(self) -> AsyncJupyterSession:
        if self._jupyter_session is not None:
            return self._jupyter_session
        if settings.PYTHON_BACKEND == "jupyter-docker-kernels":
            self._jupyter_session = ContainerJupyterSession(
                log_id=self.log_id,
                kernel_id=self.kernel_id,
                conn_info=self.conn_info,
                kernel_manager=self.kernel_manager,
                timeout=self._local_jupyter_timeout,
            )
        else:
            self._jupyter_session = InProcessJupyterSession(
                log_id=self.log_id,
                timeout=self._local_jupyter_timeout,
            )
        return self._jupyter_session

    async def _interrupt_jupyter_kernel(self) -> None:
        session = await self._resolve_jupyter_session()
        try:
            await session.interrupt()
        except Exception as e:
            msg = f"Exception in _interrupt_jupyter_kernel: {e}"
            self.logger.warning(msg, extra=self.log_extra)

    def close(self):
        if self._jupyter_session:
            self._jupyter_session.close()
            self._jupyter_session = None  # type: ignore

    async def self_destruct(self):
        await self._interrupt_jupyter_kernel()
        self.close()

    async def _process(self, message: Message) -> AsyncIterator[Message]:
        if self._execution_lock is None:
            return

        content_item = message.content[0]
        script = content_item.text if isinstance(content_item, TextContent) else ""

        # script = """
        # import time

        # counter = 0
        # print("Starting CPU-heavy loop... check your Activity Monitor/htop now!")

        # try:
        #     while True:
        #         # Tight loop: performs basic math as fast as possible
        #         counter += 1

        #         # Only print every 10 million iterations.
        #         # This ensures the CPU is the bottleneck, not the print statement.
        #         if counter % 10_000_000 == 0:
        #             print(f"CPU Pegged! Iteration: {counter}")

        # except KeyboardInterrupt:
        #     print("Interrupt received! CPU should now drop.")
        # """

        if not script:
            yield self._make_response(
                "[ERROR] No script provided.", channel=getattr(message, "channel", None)
            )
            return

        channel = getattr(message, "channel", None)
        session = await self._resolve_jupyter_session()

        async with self._execution_lock:
            # We create a TASK. This schedules the execution on the event loop.
            # This allows the execution to live independently of the 'await' below.
            execution_task = asyncio.create_task(session.execute(script))

            try:
                # asyncio.shield prevents wait_for from cancelling the execution_task
                # the moment the timeout is reached.
                output = await asyncio.wait_for(
                    asyncio.shield(execution_task), timeout=self._local_jupyter_timeout
                )
            except asyncio.TimeoutError:
                # THE TIMEOUT HIT: The kernel is likely in an infinite loop.
                await self._interrupt_jupyter_kernel()

                try:
                    # Give the kernel a few seconds to process the interrupt,
                    # finish the loop, and return the partial output collected so far.
                    # We await the original task, NOT the shield.
                    partial_output = await asyncio.wait_for(execution_task, timeout=5.0)
                    output = (
                        f"[ERROR] Execution timed out after {self._local_jupyter_timeout}s "
                        f"and was interrupted.\n\nPartial Output:\n{partial_output}"
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    # The kernel is so stuck (e.g., C-level deadlock) that even
                    # the interrupt didn't work within 5 seconds.
                    output = f"[ERROR] Execution completely timed out after {self._local_jupyter_timeout}s and couldn't be cleanly interrupted."
                except Exception as e:
                    output = f"[ERROR] Execution interrupted, but failed with: {e}"

            except (asyncio.CancelledError, GeneratorExit) as e:
                # The request was cancelled (user disconnect/external timeout)
                await self._interrupt_jupyter_kernel()
                # We must cancel the task as well, otherwise it keeps running in the background
                execution_task.cancel()
                msg = (f"Request cancelled. Kernel interrupted with {e}.",)
                self.logger.warning(msg, extra=self.log_extra)
                # raise
                output = "[ERROR]: python kernel excecuition timed out."

            except Exception as e:
                await self._interrupt_jupyter_kernel()
                execution_task.cancel()  # Clean up the task
                output = f"[ERROR]: {e}"

        yield self._make_response(output, channel=channel)
