# Tech Stack
- Python as primary programming language
- LangGraph for agent orchestration
- CopilotKit + Next.js for chat UI
- OpenAI API for LLM

# Project Setup

## Prerequisites
- Python 3.12+
- Node.js 20+
- `uv` installed
- `npm` installed

## 1) Setup and Run Agents (FastAPI + AG-UI)

From the repo root:

```bash
cd agents
uv venv
source .venv/bin/activate
uv sync
```

Create `agents/.env` with:

```env
OPENAI_API_KEY=your_openai_api_key
```

Start the agent server:

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Optional health check:

```bash
curl http://127.0.0.1:8000/agui/health
```

## 2) Setup and Run Frontend (Next.js + CopilotKit)

From the repo root:

```bash
cd frontend
npm install
```

Create `frontend/.env.local` with:

```env
AGENT_AGUI_URL=http://127.0.0.1:8000/agui
```

Start the frontend:

```bash
npm run dev
```

Open:

`http://localhost:3000`

## Development Flow
1. Run `agents` server first.
2. Run `frontend` server.
3. Chat in the UI; requests flow through CopilotKit runtime to the AG-UI FastAPI endpoint.