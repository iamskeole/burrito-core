import logging
import os
from typing import Dict, Optional

import docker

from burrito.common.utils import random_uuid

logger = logging.getLogger(__name__)


class DockerKernelManager:
    def __init__(self):
        # Connects to the proxy automatically via DOCKER_HOST env var
        self.client = docker.from_env()
        self.runtime_dir = "/tmp/jupyter-runtime"
        # State tracking: {kernel_id: 'idle' | 'busy'}
        self.pool_state: Dict[str, str] = {}

    async def refresh_pool(self):
        """Syncs local pool_state with actual running Docker containers."""
        try:
            # List all containers that match our naming convention
            containers = self.client.containers.list(filters={"name": "kernel-"})
            active_ids = set()

            for c in containers:
                # Extract kernel_id from name "kernel-uuid"
                kid = c.name.replace("kernel-", "")
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
        except Exception as e:
            logger.error(f"Error refreshing pool: {e}")

    async def spawn_one(self) -> Optional[str]:
        """Spawns a single kernel and marks it as idle."""
        try:
            kernel_id = random_uuid()
            # We map a unique file in the shared volume to the container's internal connection file
            host_conn_path = f"{self.runtime_dir}/{kernel_id}.json"

            out = self.client.containers.run(
                image="burrito-kernel:latest",
                name=f"kernel-{kernel_id}",
                detach=True,
                volumes={
                    host_conn_path: {"bind": "/tmp/connection.json", "mode": "rw"}
                },
                mem_limit="2g",
                cpu_quota=50000,
                user="1000:100",
                network_mode="bridge",
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
            container = self.client.containers.get(f"kernel-{kernel_id}")
            container.stop(timeout=2)
            container.remove()

            # Cleanup the shared volume file
            path = f"{self.runtime_dir}/{kernel_id}.json"
            if os.path.exists(path):
                os.remove(path)

            self.pool_state.pop(kernel_id, None)
        except Exception as e:
            logger.debug(f"Cleanup failed for {kernel_id}: {e}")

    def get_connection_info(self, kernel_id: str) -> str:
        """Reads the connection JSON written by the kernel container."""
        path = f"{self.runtime_dir}/{kernel_id}.json"
        # We might need a small retry loop here if called immediately after spawn
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Kernel {kernel_id} has not written its connection file yet."
            )
