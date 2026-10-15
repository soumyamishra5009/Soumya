from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging

# Load .env from the project root (works regardless of CWD)
try:
    from dotenv import load_dotenv

    _here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_here, ".env"))
    load_dotenv(os.path.join(_here, "..", "..", ".env"))
except Exception:  # dotenv is optional
    pass

from app.api.v1.api import api_router
from app.core.config import settings

logger = logging.getLogger("syncforge")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables for local dev (use Alembic in production)
    print("SyncForge AI API starting up...")
    try:
        from app.core.database import init_db

        init_db()
        print("Database tables ready (" + settings.DATABASE_URL.split("://")[0] + ")")
    except Exception as exc:
        print("WARNING: could not initialize database: " + str(exc))
    yield
    # Shutdown
    print("SyncForge AI API shutting down...")


app = FastAPI(
    title="SyncForge AI API",
    description="API for AI-powered Meetings → Decisions → Tasks → Code → Verification workflow",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "SyncForge AI API",
        "version": "0.1.0",
        "status": "active",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    db_status = "ok"
    try:
        from sqlalchemy import text
        from app.core.database import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error: " + str(exc)
    return {"status": "healthy", "service": "syncforge-api", "database": db_status}


app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
