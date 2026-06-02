# Mnemo

**Privacy-First Screenshot Intelligence Organizer**

Mnemo is a local-first, AI-powered system designed to process, tag, and organize your screenshots without sending your personal data to external clouds (unless explicitly configured). It uses native Vision LLMs (via Ollama) to extract context, text, and semantic meaning from images, making your entire screenshot gallery instantly searchable.

---

## Architecture

Mnemo is composed of three main layers:
1. **FastAPI Backend**: The core engine. It manages SQLite data, ChromaDB embeddings, local file watching, and orchestrates the Ollama (Vision) and Telnyx (Text Embeddings) API calls.
2. **Desktop UI (CustomTkinter)**: A lightweight, cross-platform Python interface to browse the gallery, perform semantic searches, manage bulk operations, and configure settings.
3. **Mobile App (Expo/React Native)**: A fast, WiFi-connected mobile client. It syncs with your desktop seamlessly by scanning a QR Code, allowing you to upload screenshots directly from your phone's gallery into Mnemo.

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.12+**
- **Node.js 18+** (for Mobile app)
- **Ollama** installed on your host machine ([Download Ollama](https://ollama.com/))
  - Pull a vision model: `ollama run gemma3:4b`

### 2. Backend & Desktop Setup

1. **Clone and Setup Virtual Environment:**
   ```bash
   git clone <repo-url>
   cd Mnemo
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install Dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```
3. **Initialize the Database:**
   ```bash
   cd backend
   alembic upgrade head
   cd ..
   ```
4. **Launch the Desktop App:**
   ```bash
   python desktop/main.py
   ```
   *The backend server will start automatically on an available port (8765-8770).*

### 3. Mobile App Setup

1. In a new terminal, navigate to the `mobile` directory:
   ```bash
   cd mobile
   npm install
   npx expo start
   ```
2. Install **Expo Go** on your iOS/Android device.
3. Scan the Expo QR code in your terminal.
4. Once the app opens, go to **Settings** and tap **Scan QR Code**.
5. In the Desktop App, click **QR Code** in the top bar and scan it with your phone.

---

## ⚙️ Configuration & Environment

The backend accepts configuration via `.env` in the `backend/` directory, or it creates a default SQLite store if none is provided.

```env
MNEMO_DB_URL=sqlite+aiosqlite:///data/mnemo.db
MNEMO_CHROMA_PATH=data/chroma
MNEMO_OLLAMA_BASE_URL=http://127.0.0.1:11434
MNEMO_OLLAMA_MODEL=gemma4:e4b
# Telnyx API key is only needed for embeddings.
MNEMO_TELNYX_API_KEY=your_key_here
```

## 🐳 Docker (Optional)

If you prefer to run the backend isolated from the desktop UI:

```bash
docker-compose up -d
```
*Note: This relies on Ollama running on your host machine to leverage GPU acceleration natively.*

---

## 🔒 Security

- Rate Limiting is enabled (100 req/min) via SlowAPI to prevent accidental local abuse loops.
- API endpoints are protected by `X-API-Key`, generated securely on startup if not explicitly provided.

---

## 🧪 Testing

Run the integration and unit tests using `pytest`:

```bash
PYTHONPATH=backend .venv/bin/pytest --cov=app backend/tests/
```

We guarantee **> 80% coverage** on all critical paths.
