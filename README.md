# Mnemo — Privacy-First Screenshot Intelligence Organizer

Local AI-powered screenshot analysis, organization, and semantic search.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your Telnyx API key (optional)

# 4. Start Ollama (requires separate installation)
ollama pull gemma3:4b
ollama serve

# 5. Start Mnemo backend
cd backend && uvicorn app.main:app --reload
```

## Architecture

- **Backend**: FastAPI + SQLite + ChromaDB
- **LLM**: Ollama (Gemma 4 Vision) — runs locally
- **Embeddings**: Telnyx API (semantic search) or full-text fallback
- **Desktop**: CustomTkinter
- **Mobile**: Expo / React Native (remote client via WiFi)
