import asyncio
import hashlib
import inspect
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Callable, Generic, Iterator, Optional, TypeVar, Union

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.handlers.kernel_handler import DockerKernelManager
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython, refresh_python_internet_flag

K = TypeVar("K")
V = TypeVar("V")


def cleanup_tool(_key: str, tool: Any) -> None:
    """Safely close the tool when it gets evicted from the cache."""

    # 1 handle the ASYNC cleanup (interrupting the kernel)
    if hasattr(tool, "self_destruct") and inspect.iscoroutinefunction(
        tool.self_destruct
    ):
        try:
            # schedule the async self_destruct on the current loop without blocking.
            asyncio.create_task(tool.self_destruct())
        except RuntimeError:
            # this happens if the loop is already closed (eg during final app shutdown)
            # in that case, we fallback to the synchronous close()
            if hasattr(tool, "close") and callable(tool.close):
                tool.close()
        return

    # 2 fallback for tools that are purely synchronous
    if hasattr(tool, "close") and callable(tool.close):
        tool.close()


class SessionCache(Generic[K, V]):
    def __init__(
        self,
        maxsize: int,
        on_evict: Optional[Callable[[K, V], None]],
        log_id: str,
        tool_type: str,
    ):
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = log_id
        self.log_extra = {"log_id": self.log_id}
        self.maxsize = maxsize
        self.tool_type = tool_type
        # Internal storage: {key: (value, last_access_time)}
        self._data: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._disabled = maxsize <= 0
        self._on_evict = on_evict
        self._lock = threading.Lock()

    def __setitem__(self, key: K, value: V) -> None:
        to_evict = None  # Store item to evict here
        reason = ""

        with self._lock:
            if self._disabled:
                return

            if key in self._data:
                old_value, _ = self._data[key]
                self._data.move_to_end(key)
                self._data[key] = (value, time.time())
                if old_value is not value:
                    to_evict = (key, old_value)
                    reason = "SET EXISTING"
            else:
                if len(self._data) >= self.maxsize:
                    evicted_key, (evicted_value, _) = self._data.popitem(last=False)
                    to_evict = (evicted_key, evicted_value)
                    reason = "SET NEW"
                self._data[key] = (value, time.time())

        # EXECUTE EVICTION OUTSIDE THE LOCK
        if to_evict:
            self._perform_evict(to_evict[0], to_evict[1], reason)

        if settings.DEBUG_SESSION_CACHE:
            self.logger.debug(f"SET: {key} => {value}", extra=self.log_extra)

    def __delitem__(self, key: K) -> None:
        to_evict = None
        with self._lock:
            if key in self._data:
                old_value, _ = self._data.pop(key)
                to_evict = (key, old_value)

        if to_evict:
            self._perform_evict(to_evict[0], to_evict[1], "DELETE")

    def __getitem__(self, key: K) -> V:
        with self._lock:
            value, _ = self._data[key]
            self._data[key] = (value, time.time())
            self._data.move_to_end(key)

            if settings.DEBUG_SESSION_CACHE:
                self.logger.debug(
                    f"GET (__getitem__): {key} => {value}", extra=self.log_extra
                )

            return value

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        with self._lock:
            if key in self._data:
                # We manually trigger the logic from __getitem__ to keep locks and logs consistent
                value, _ = self._data[key]
                self._data[key] = (value, time.time())
                self._data.move_to_end(key)

                if settings.DEBUG_SESSION_CACHE:
                    self.logger.debug(
                        f"GET (HIT): {key} => {value}", extra=self.log_extra
                    )
                return value

            if settings.DEBUG_SESSION_CACHE:
                self.logger.debug(
                    f"GET (MISS): {key} => {default}", extra=self.log_extra
                )
            return default

    def evict_idle(self, timeout_seconds: float) -> int:
        if self._disabled:
            return 0

        evicted_items = []  # List of (key, value)
        now = time.time()

        with self._lock:
            keys_to_remove = []
            for key, (_, last_access) in self._data.items():
                if now - last_access > timeout_seconds:
                    keys_to_remove.append(key)
                else:
                    break

            for key in keys_to_remove:
                val, _ = self._data.pop(key)
                evicted_items.append((key, val))

        # EXECUTE ALL EVICTIONS OUTSIDE THE LOCK
        for key, val in evicted_items:
            if val is not None:
                self._perform_evict(key, val, f"IDLE TIMEOUT [{self.tool_type}]")

        return len(evicted_items)

    def _perform_evict(self, key: K, value: V, reason: str) -> None:
        """Internal helper to execute the eviction callback safely."""
        if settings.DEBUG_SESSION_CACHE:
            self.logger.debug(f"EVICT {reason}: {key} => {value}", extra=self.log_extra)

        # guard against none here so pylance is happy
        # and callers don't have to repeat this check
        if self._on_evict is not None:
            try:
                self._on_evict(key, value)
            except Exception as e:
                self.logger.warning(
                    f"Exception: EVICT {reason}: {e}", extra=self.log_extra
                )

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def keys(self) -> list[K]:
        with self._lock:
            return list(self._data.keys())

    def items(self) -> list[tuple[K, tuple[V, float]]]:
        with self._lock:
            return list(self._data.items())

    def values(self) -> list[tuple[V, float]]:
        with self._lock:
            return list(self._data.values())

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            return iter(list(self._data.keys()))

    def clear(self) -> None:
        items_to_clear = []
        with self._lock:
            while self._data:
                key, (value, _) = self._data.popitem(last=False)
                items_to_clear.append((key, value))

        for key, val in items_to_clear:
            if val is not None:
                self._perform_evict(key, val, "SHUTDOWN")

    def setdefault(self, key: K, value: V) -> V:
        """Set key to value ONLY if key is not already present.
        Returns the existing value if present, otherwise the new value.
        This is atomic — prevents overwriting live tools with sentinels."""
        to_evict = None

        with self._lock:
            if self._disabled:
                return value

            if key in self._data:
                existing, _ = self._data[key]
                self._data[key] = (existing, time.time())
                self._data.move_to_end(key)

                if settings.DEBUG_SESSION_CACHE:
                    self.logger.debug(
                        f"SETDEFAULT (EXISTS): {key} => {existing}",
                        extra=self.log_extra,
                    )
                return existing

            # Key is absent — insert, possibly evicting LRU
            if len(self._data) >= self.maxsize:
                evicted_key, (evicted_value, _) = self._data.popitem(last=False)
                to_evict = (evicted_key, evicted_value)
            self._data[key] = (value, time.time())

        # EXECUTE EVICTION OUTSIDE THE LOCK
        if to_evict:
            self._perform_evict(to_evict[0], to_evict[1], "SET DEFAULT")

        if settings.DEBUG_SESSION_CACHE:
            self.logger.debug(
                f"SETDEFAULT (NEW): {key} => {value}", extra=self.log_extra
            )
        return value


class SessionHandler:
    kernel_handler: Optional[DockerKernelManager] = None

    def __init__(self, log_id: str):
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_id = log_id
        self.log_extra = {"log_id": self.log_id}

        ms_browser = settings.BROWSER_SESSION_CACHE_SIZE
        ms_python = settings.PYTHON_SESSION_CACHE_SIZE

        self.python_tools: SessionCache[str, Optional[Union[BurritoPython, str]]] = (
            SessionCache(
                maxsize=ms_python,
                on_evict=cleanup_tool,
                log_id=self.log_id,
                tool_type="python",
            )
        )

        self.browser_tools: SessionCache[str, Optional[Union[BurritoBrowser, str]]] = (
            SessionCache(
                maxsize=ms_browser,
                on_evict=None,
                log_id=self.log_id,
                tool_type="browser",
            )
        )

        self._maintenance_task: Optional[asyncio.Task] = None

        if settings.PYTHON_BACKEND == "jupyter-docker-kernels":
            self.kernel_handler = DockerKernelManager()

    async def start_maintenance(self):
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def _manage_kernels(self):
        if self.kernel_handler is None:
            return 0

        num_kernels = await self.kernel_handler.refresh_pool()
        return num_kernels

    async def _maintenance_loop(self) -> None:
        check_interval = settings.SESSION_HANDLER_SENTINEL_HEARTBEAT_SECONDS
        py_timeout = settings.PYTHON_SESSION_IDLE_TIMEOUT
        br_timeout = settings.BROWSER_SESSION_IDLE_TIMEOUT

        while True:
            try:
                py_evicted = self.python_tools.evict_idle(py_timeout)
                br_evicted = self.browser_tools.evict_idle(br_timeout)

                if settings.IS_PYTHON_TOOL_AVAILABLE:
                    await refresh_python_internet_flag()

                num_kernels = await self._manage_kernels()

                if settings.DEBUG_SESSION_CACHE and (py_evicted > 0 or br_evicted > 0):
                    msg = (
                        f"Cleaned up "
                        f"{py_evicted} python and "
                        f"{br_evicted} browser sessions. "
                        f"{num_kernels} kernels for Python are active."
                    )
                    self.logger.debug(msg, extra=self.log_extra)

            except Exception as e:
                self.logger.error(f"Error in session maintenance loop: {e}")
            await asyncio.sleep(check_interval)

    def hash_prompt(self, prompt: str) -> str:
        hash_bytes = hashlib.sha256(prompt.encode()).digest()
        return str(uuid.UUID(bytes=hash_bytes[:16]))

    def set_python_tool(
        self, session_id: str, tool: Optional[Union[BurritoPython, str]]
    ) -> None:
        self.python_tools[session_id] = tool

    def set_browser_tool(
        self, session_id: str, tool: Optional[Union[BurritoBrowser, str]]
    ) -> None:
        self.browser_tools[session_id] = tool

    def get_python_tool(self, session_id: str) -> Optional[Union[BurritoPython, str]]:
        return self.python_tools.get(session_id)

    def get_browser_tool(self, session_id: str) -> Optional[Union[BurritoBrowser, str]]:
        return self.browser_tools.get(session_id)

    async def shutdown(self) -> None:
        if self._maintenance_task:
            self._maintenance_task.cancel()
        try:
            self.python_tools.clear()
            self.browser_tools.clear()
        except Exception as e:
            print(f"Exception in SessionHandler.shutdown: {e}")
