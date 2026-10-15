#!/usr/bin/env bash
# Setup PostgreSQL + Redis via Docker for SyncForge AI
set -e

echo "🐘 SyncForge AI - Database & Redis Setup"
echo "========================================="

if ! command -v docker &> /dev/null; then
  echo "❌ Docker is not installed. Install Docker Desktop first."
  exit 1
fi

echo "🚀 Starting Postgres (pgvector) and Redis..."
docker compose up -d postgres redis

echo "⏳ Waiting for Postgres to be ready..."
until docker exec syncforge-postgres pg_isready -U postgres > /dev/null 2>&1; do
  sleep 1
done

echo "🧩 Enabling pgvector extension..."
docker exec -i syncforge-postgres psql -U postgres -d syncforge -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo ""
echo "✅ Postgres ready at localhost:5432 (db: syncforge)"
echo "✅ Redis ready at localhost:6379"
echo ""
echo "Next: cd apps/api && python -m venv venv && pip install -r requirements.txt"
