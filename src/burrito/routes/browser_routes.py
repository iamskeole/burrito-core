from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any

from burrito.common.dependencies import (
    BrowserHandler, 
    get_browser_handler
)

router = APIRouter()

class BrowserRequest(BaseModel):
    user_id: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)

@router.post("/v1/tools/browser")
async def browser_tool_endpoint(
    request: BrowserRequest,
    browser_handler: BrowserHandler = Depends(get_browser_handler),
) -> Dict[str, Any]:

    # Delegate everything to the handler facade
    import time
    t0 = time.time()
    res = await browser_handler.perform_action(
        request.user_id, 
        request.action, 
        request.params
    )
    t1 = time.time()
    td = t1 - t0
    _len = len(res["content"])
    print(f"Browser request took {td:.2f} seconds and produced len={_len:,} result:\n{res['content'][:300]}")
    return res