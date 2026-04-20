import gc
import logging
import os
import random
from typing import Dict, Optional

import docker

from burrito.common.config import settings
from burrito.common.utils import random_uuid

logger = logging.getLogger(__name__)


class DockerKernelManager:
    def __init__(self):
        # Connects to the proxy automatically via DOCKER_HOST env var
        self.client = docker.from_env()
        self.runtime_dir = "/tmp/jupyter-runtime"
        # State tracking: {kernel_id: 'idle' | 'busy'}
        self.pool_state: Dict[str, str] = {}

    async def _rightsize_pool(self):
        min_pool_size = settings.PYTHON_KERNEL_MIN_POOL_SIZE
        current_count = len(self.pool_state)
        num_acquired = 0
        num_released = 0

        if current_count < min_pool_size:
            for _ in range(min_pool_size - current_count):
                await self.spawn_one()
                num_acquired += 1

        if current_count > min_pool_size:
            for _ in range(current_count - min_pool_size):
                kernel_id = await self._release_one(destroy=True)
                num_released += 1
        logger.info(f"{num_acquired=} {num_released=}")
        updated_count = len(self.pool_state)
        return updated_count

    async def refresh_pool(self):
        """Syncs local pool_state with actual running Docker containers."""
        try:
            # List all containers that match our naming convention
            containers = self.client.containers.list(
                filters={"name": "burrito-kernel-"}
            )
            active_ids = set()

            for c in containers:
                # Extract kernel_id from name "burrito-kernel-uuid"
                kid = c.name.replace("burrito-kernel-", "")
                active_ids.add(kid)
                # If we don't know this kernel, assume it's idle
                if kid not in self.pool_state:
                    self.pool_state[kid] = "idle"

            # Remove kernels from state that are no longer running
            self.pool_state = {
                kid: status
                for kid, status in self.pool_state.items()
                if kid in active_ids
            }
            await self._rightsize_pool()
            gc.collect()
            # TODO: need to have extra in pool, since agent may return before idle timeout
            # which means there's some small chance agent 1 gets kernel of agent 2
            # so need to keep track of a stale flag somehow?
            # so probably on session handler evict idle we need to flag them as 'stale' or used
            # and only evict those here?
        except Exception as e:
            logger.error(f"Error refreshing pool: {e}")

    async def _release_one(self, destroy: bool = False) -> Optional[str]:
        idle_kernels = [i for i in self.pool_state if self.pool_state[i] == "idle"]
        kernel_id = random.choice(idle_kernels)
        await self.release_kernel(kernel_id, destroy)
        return kernel_id

    async def spawn_one(self) -> Optional[str]:
        """Spawns a single kernel and marks it as idle."""
        try:
            kernel_id = random_uuid()[:6]

            out = self.client.containers.run(
                image="burrito-kernel:latest",
                name=f"burrito-kernel-{kernel_id}",
                detach=True,
                environment={"KERNEL_ID": kernel_id},
                mem_limit="2g",
                user="1000:100",
                network="burrito-internal",
                stdin_open=True,
                tty=True,
            )

            self.pool_state[kernel_id] = "idle"
            logger.info(f"Pre-warmed kernel spawned: {kernel_id}")
            return kernel_id
        except Exception as e:
            logger.error(f"Failed to spawn kernel: {e}")
            return None

    async def acquire_kernel(self) -> str:
        """Leases an idle kernel or bursts a new one if none are available."""
        await self.refresh_pool()

        # 1. Try to find an idle one
        for kid, status in self.pool_state.items():
            if status == "idle":
                self.pool_state[kid] = "busy"
                return kid

        # 2. Burst: Spawn a new one immediately if pool is empty/busy
        logger.info("All kernels busy. Bursting a new one...")
        kid = await self.spawn_one()
        if kid:
            self.pool_state[kid] = "busy"
            return kid
        raise RuntimeError("Could not spawn a Docker kernel.")

    async def release_kernel(self, kernel_id: str, destroy: bool = True):
        """Returns a kernel to the idle pool or destroys it."""
        if destroy:
            await self.kill_kernel(kernel_id)
        else:
            self.pool_state[kernel_id] = "idle"

    async def kill_kernel(self, kernel_id: str):
        """Stops and removes the container and its connection file."""
        try:
            container = self.client.containers.get(f"burrito-kernel-{kernel_id}")
            container.stop(timeout=2)
            container.remove()

            # Cleanup the shared volume file
            path = f"/tmp/jupyter-runtime/{kernel_id}.json"
            if os.path.exists(path):
                os.remove(path)

            self.pool_state.pop(kernel_id, None)
        except Exception as e:
            logger.debug(f"Cleanup failed for {kernel_id}: {e}")

    async def get_connection_info(self, kernel_id: str) -> str:
        """Reads the connection JSON written by the kernel container via Docker API."""
        import asyncio
        import io
        import tarfile

        container = self.client.containers.get(f"burrito-kernel-{kernel_id}")

        for _ in range(50):
            try:
                bits, stat = container.get_archive(
                    f"/tmp/jupyter-runtime/{kernel_id}.json"
                )
                file_content = b"".join(bits)

                with tarfile.open(fileobj=io.BytesIO(file_content)) as tar:
                    member = tar.next()
                    if member:
                        f = tar.extractfile(member)
                        if f:
                            content = f.read().decode("utf-8")
                            if content:
                                return content
            except docker.errors.NotFound:
                pass
            except Exception as e:
                pass

            await asyncio.sleep(0.1)

        raise FileNotFoundError(
            f"Kernel {kernel_id} has not written its connection file yet."
        )
