from __future__ import annotations
import uvicorn
from burrito.main import app

def main():
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="debug"
    )

if __name__ == "__main__":
    main()