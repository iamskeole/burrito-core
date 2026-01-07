import uvicorn
from fastapi import APIRouter, FastAPI, Depends
from sqlalchemy.orm import Session

from contextlib import asynccontextmanager

from burrito.types.sandbox import SandboxRequest
from burrito.sandbox import Sandbox, settings
from burrito.database.database import get_db

sandbox_manager = Sandbox()

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # On startup
#     print("Application starting up...")
#     init_database()
#     yield
#     # On shutdown
#     print("Application shutting down...")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code here runs on startup
    print("Application starting up...")
    # The sandbox_manager is already initialized and its thread is running
    yield
    # Code here runs on shutdown
    print("Application shutting down...")
    sandbox_manager.shutdown() # Gracefully shut down all kernels


app = FastAPI(title="burrito:sandbox", version="0.1.0", lifespan=lifespan)

router = APIRouter(
    prefix="/sandbox",
    tags=["Sandbox"]
)


@router.post("/run")
async def run_code(request: SandboxRequest, db: Session = Depends(get_db)):
    x = 1
    return {"ok": True, "result": "todo"}
    session_path = SESSIONS_DIR / req.session_id
    session_path.mkdir(parents=True, exist_ok=True)
    notebook_path = session_path / "history.ipynb"

    # Get or create kernel
    if req.session_id not in _sessions:
        kernel = SessionKernel(req.session_id)
        if req.replay:  # TODO: figure out replay from client (also, in client)
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
