from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ignore unrelated keys that live in the shared .env (e.g. web-only vars)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "SyncForge AI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    
    # Database
    # Default to SQLite for zero-setup local dev. Set DATABASE_URL to a
    # postgres+pgvector URL in production (see .env.example).
    DATABASE_URL: str = "sqlite:///./syncforge.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    # Security
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Auth
    AUTH_SECRET: str = "your-super-secret-auth-key-change-this-in-prod"
    
    # LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_CHAT_MODEL: str = "llama3.1:8b"
    DEFAULT_SUMMARY_MODEL: str = "llama3.1:8b"
    DEFAULT_FAST_MODEL: str = "llama3.1:8b"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # When no LLM is reachable (no Ollama, no API key) fall back to an offline
    # extractive summary so the pipeline always completes.
    ALLOW_EXTRACTIVE_FALLBACK: bool = True
    EMBEDDING_MODEL: str = "nomic-embed-text"
    OPENROUTER_API_KEY: str = ""
    CODE_MODEL: str = "qwen2.5-coder:7b"
    AGENT_MODEL: str = "deepseek-coder:6.7b"
    ENABLE_MODEL_ROUTING: bool = True
    
    # STT
    STT_ENGINE: str = "whisper_local"
    WHISPER_MODEL: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"
    
    # Storage
    STORAGE_TYPE: str = "local"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100

    # Dev Studio (Phase 3) — sandboxed, per-workspace code tree on disk.
    # Files live under DEVSTUDIO_ROOT/<workspace_id>/ so later phases (test
    # runs, git) can operate on real files without touching the host project.
    DEVSTUDIO_ROOT: str = "./devstudio"
    DEVSTUDIO_MAX_FILE_KB: int = 512
    DEVSTUDIO_MAX_FILES: int = 2000
    DEVSTUDIO_MAX_DEPTH: int = 8
    # How many characters of a file to include as context for the AI chat.
    DEVSTUDIO_CONTEXT_CHARS: int = 12000
    
    # Code Execution
    CODE_EXECUTOR: str = "judge0"
    JUDGE0_BASE_URL: str = "http://localhost:2358"
    JUDGE0_API_KEY: str = ""
    E2B_API_KEY: str = ""
    EXEC_TIMEOUT_SECONDS: int = 30
    EXEC_MAX_MEMORY_MB: int = 512
    
    # Vector Search
    VECTOR_DIMENSION: int = 768
    SIMILARITY_THRESHOLD: float = 0.7
    
    # GitHub
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_TOKEN: str = ""
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_TIME_LIMIT: int = 3600
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3000

    # Security
    REQUIRE_CONSENT_FOR_RECORDINGS: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    MAX_TRANSCRIPT_CHARS: int = 500_000
    EXEC_MAX_CPU_PERCENT: int = 50


settings = Settings()
