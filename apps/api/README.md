# SyncForge AI - Backend API

FastAPI backend for SyncForge AI. Handles meetings, tasks, AI agents, code execution and RAG.

## Tech Stack

- **FastAPI** - Web framework
- **SQLAlchemy** + **Alembic** - ORM & Migrations
- **PostgreSQL** + **pgvector** - Database + Vector Search
- **Celery** + **Redis** - Background Jobs
- **faster-whisper** - Local STT
- **Ollama** - Local LLMs
- **Instructor** - Structured LLM Outputs

## Project Structure

```text
app/
├── api/v1/      # API routes
├── core/        # Config, security, logging
├── models/      # SQLAlchemy models
├── schemas/     # Pydantic schemas
├── crud/        # DB operations
├── services/    # Business logic (STT, LLM, RAG, GitHub)
├── workers/     # Celery tasks
└── utils/       # Helpers
```

## Getting Started

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Set up .env
cp ../../.env.example .env

# Run development server
uvicorn main:app --reload --port 8000
```

## API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health
