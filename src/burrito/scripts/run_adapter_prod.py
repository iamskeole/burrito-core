from __future__ import annotations

import os

import uvicorn
from burrito.main import app


def start():
    """Runs the Uvicorn server in production mode."""
    host = os.getenv("BURRITO_HOST", "0.0.0.0")
    port_str = os.getenv("BURRITO_PORT", "8000")

    try:
        port = int(port_str)
    except ValueError:
        print(f"Error: Invalid port '{port_str}'. Defaulting to 8000.")
        port = 8000

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start()
