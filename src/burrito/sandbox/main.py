import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from burrito.sandbox.dependencies import sandbox_manager
from burrito.sandbox.routes import execution

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Sandbox service is starting up...")
    yield
    print("Sandbox service is shutting down...")
    sandbox_manager.shutdown()

app = FastAPI(
    title="Burrito Sandbox Service",
    description="A dedicated service for executing code in isolated kernels.",
    lifespan=lifespan
)

app.include_router(execution.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=False, log_level="debug")
