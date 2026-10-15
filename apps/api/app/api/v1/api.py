from fastapi import APIRouter

from app.api.v1 import auth, workspaces, meetings, tasks

api_router = APIRouter()

api_router.include_router(auth.router, prefix="")
api_router.include_router(workspaces.router, prefix="")
api_router.include_router(meetings.router, prefix="")
api_router.include_router(tasks.router, prefix="")

# Planned (Phase 3/4): agents, code, memory
# api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
# api_router.include_router(code.router, prefix="/code", tags=["code"])
# api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
