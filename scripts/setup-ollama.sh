#!/usr/bin/env bash
# Setup Ollama models for SyncForge AI
set -e

echo "🧠 SyncForge AI - Ollama Model Setup"
echo "===================================="

if ! command -v ollama &> /dev/null; then
  echo "❌ Ollama is not installed. Install from https://ollama.com/download"
  exit 1
fi

echo "📦 Pulling models (this may take a while)..."
ollama pull llama-3.1:8b          # fast utilities
ollama pull llama-3.3:70b         # summaries / extraction
ollama pull qwen2.5-coder:7b      # code generation
ollama pull deepseek-coder:6.7b   # agent
ollama pull nomic-embed-text      # embeddings

echo ""
echo "✅ Available models:"
ollama list

echo ""
echo "Done. Make sure OLLAMA_BASE_URL=http://localhost:11434 in your .env"
