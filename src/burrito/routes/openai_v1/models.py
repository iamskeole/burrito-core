from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/v1/models")
async def v1_responses() -> JSONResponse:
    return JSONResponse({"models": "todo"})
