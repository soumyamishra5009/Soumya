from fastapi import APIRouter

from app.api.v1 import agent, auth, code, demo, meetings, memory, ship, system, tasks, verify, workspaces

api_router = APIRouter()

api_router.include_router(auth.router, prefix="")
api_router.include_router(workspaces.router, prefix="")
api_router.include_router(meetings.router, prefix="")
api_router.include_router(tasks.router, prefix="")
api_router.include_router(code.router, prefix="")
api_router.include_router(ship.router, prefix="")
api_router.include_router(agent.router, prefix="")
api_router.include_router(verify.router, prefix="")
api_router.include_router(memory.router, prefix="")
api_router.include_router(system.router, prefix="")
api_router.include_router(demo.router, prefix="")

# Planned (Phase 5+): memory (project RAG)
# api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
