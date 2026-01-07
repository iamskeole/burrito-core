from fastapi import APIRouter, Depends


from burrito.types.sandbox import SandboxRequest, SandboxResponse
from burrito.sandbox.dependencies import sandbox_manager

router = APIRouter()


@router.post("/execute", response_model=SandboxResponse)
async def run_code(request: SandboxRequest):
    out = sandbox_manager.run(request)
    return out


# TODO: i don't need a dedicated route / app for sandbox (yet)
# just use it as a class in the adapter, manage it by session
# goal is to have a self sufficient standalone app that wraps around gpt-oss
# and maybe the non-open-source version will do all the "enterprise" stuff
# eg database, session lifespan etc