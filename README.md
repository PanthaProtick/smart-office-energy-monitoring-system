# Smart Office Energy Monitoring System

A full-stack simulation and monitoring platform for a smart office. A FastAPI
backend simulates device activity across three rooms, tracks power/energy
consumption in real time, evaluates alert rules, and pushes live updates to a
React dashboard over WebSockets and to Discord via a bot and a webhook.

## How it works

A background simulator randomly toggles devices in the backend every 10s,
which drives everything else:

```
Simulator → Device/Alert state (SQLite) → WebSocket broadcast → React dashboard (live)
```

New alerts run through their own pipeline, entirely server-side, ending in
a Discord notification:

```
Alert Engine → Alert Service → Gemini Service → Discord Service → Discord Channel
               (detects rule)   (AI summary)      (webhook)
```

The React dashboard and the Discord bot are two independent clients of the
same backend — both read/act through its REST API (plus a WebSocket for
the dashboard's live updates); neither touches SQLite or Gemini directly.

- **Backend** (`backend/`) — FastAPI + SQLite (SQLAlchemy). A background
  simulator randomly toggles devices, an energy service integrates power
  draw over time, and an alert engine evaluates rules (power exceeded, a
  room fully active for 2+ hours, devices left on after hours, sustained
  high power). New alerts are summarized by Google Gemini and pushed to
  Discord via a webhook; everything degrades gracefully if Gemini or
  Discord is unavailable.
- **Frontend** (`frontend/`) — React + Vite dashboard showing live device
  state, power/energy metrics, and alerts, updated over a WebSocket
  connection to the backend.
- **Discord client** (`discord_client/`) — a standalone `discord.py` bot
  exposing slash commands (`/status`, `/power`, `/alerts`, `/room`,
  `/analyze`) that call the backend's REST API. It's a separate path from
  the webhook-based automatic alert notifications above.

Further diagrams: [`High_Level_System_Architecture.png`](./High_Level_System_Architecture.png),
[`Data_Flow.png`](./Data_Flow.png), [`Hardware_Schematic.png`](./Hardware_Schematic.png).

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (manages the backend's environment)
- Node.js 18+ and npm (frontend)
- A Discord application/bot token, and optionally a Discord webhook, if you
  want Discord integration
- A Gemini API key ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)), optional — AI summaries fall back to a deterministic template without one

## Installation

### 1. Backend (managed by `uv`)

```bash
cd backend
uv sync                                    # installs deps into backend/.venv from uv.lock

cp .env.example .env                       # then fill in GEMINI_API_KEY / DISCORD_WEBHOOK_URL

uv run python -m app.database.init_db      # creates office.db and its tables
uv run python -m app.database.seed         # seeds 3 rooms with 5 devices each (3 lights, 2 fans)

uv run uvicorn app.main:app --reload       # serves http://127.0.0.1:8000
```

| Variable              | Required | Description                                                             |
|-----------------------|----------|---------------------------------------------------------------------------|
| `GEMINI_API_KEY`      | yes       | Enables AI-generated summaries; without it, template text is used instead. |
| `DISCORD_WEBHOOK_URL` | yes       | Enables automatic Discord notifications when a new alert fires.           |

For Discord_Webhook_URL, go to desired text-channels go to settings then integration then create a webhook. Copy URL and Paste in .env

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                                # serves http://localhost:5173
```

The dev server proxies `/devices`, `/rooms`, `/power`, and `/alerts` to
`http://127.0.0.1:8000` and connects to the backend's WebSocket at
`ws://127.0.0.1:8000/ws` by default — no `.env` needed for local
development. To point at a different backend, set `VITE_API_BASE_URL` and
`VITE_WS_URL`.

### 3. Discord client (managed by a local `.venv`)

```bash
cd discord_client
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                       # then fill in DISCORD_TOKEN

python bot.py
```

| Variable           | Required | Description                                                        |
|--------------------|----------|-------------------------------------------------------------------------|
| `DISCORD_TOKEN`    | yes      | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications). |
| `BACKEND_URL`      | yes      | Base URL of the running FastAPI backend, e.g. `http://localhost:8000`.  |
| `DISCORD_GUILD_ID` | no       | Syncs slash commands to one server instantly instead of globally (up to 1h). |

## Running everything together

Start the three pieces in order — each is independent, but the frontend and
bot both call the backend:

1. Backend: `cd backend && uv run uvicorn app.main:app --reload`
2. Frontend: `cd frontend && npm run dev`
3. Discord bot: `cd discord_client && source .venv/bin/activate && python bot.py`

## Testing

```bash
cd backend
uv run pytest
```

## Project structure

```
.
├── backend/            # FastAPI app, SQLite models, services, tests (uv)
├── frontend/            # React + Vite dashboard (npm)
└── discord_client/       # Standalone discord.py bot (venv + pip)
```

See `discord_client/README.md` for a full breakdown of the bot's commands
and internal layering.
