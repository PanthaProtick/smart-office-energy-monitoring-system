# Smart Office Discord Client

A standalone Discord bot that lets facility staff query office status
straight from Discord, using slash commands. It never touches the
database or any business logic directly -- every command is a thin REST
call to the FastAPI backend, which remains the single source of truth.

```
                     Discord User
                           │
                    Slash Commands
                           │
                           ▼
                 Discord Client (this app)
                           │
                     REST API Calls
                           │
                           ▼
                  FastAPI Backend
```

Automatic alert notifications (posted to a Discord channel when the
backend detects a new alert) are a **separate** path, handled entirely by
the backend's `app/services/discord_service.py` via a Discord webhook. This
bot is not involved in that path at all -- see "Automatic alert
notifications" below.

## Project structure

```
discord_client/
│
├── bot.py                    # Entrypoint: builds the bot, registers commands, logs in
├── config.py                 # Reads DISCORD_TOKEN / BACKEND_URL / etc. from the environment
├── requirements.txt
├── .env.example
│
├── commands/                 # One file per slash command
│   ├── status.py              # /status
│   ├── power.py                # /power
│   ├── alerts.py               # /alerts
│   ├── room.py                  # /room
│   └── analyze.py               # /analyze
│
├── services/
│   └── backend_client.py     # The ONLY code that calls the backend (httpx)
│
└── utils/
    └── embeds.py              # Turns backend JSON into discord.Embed objects
```

Each layer has one job:

- **`commands/`** decides *when* to call the backend and *what* to do with
  errors. It contains no formatting logic.
- **`services/backend_client.py`** decides *how* to call the backend
  (REST, `httpx`, retries/timeouts). It contains no Discord-specific code
  and no formatting logic.
- **`utils/embeds.py`** decides *how the result looks*. It never makes a
  network call.

This split means adding a new command is just: add a method to
`BackendClient` if needed, write a small `commands/<name>.py`, add a
formatter to `embeds.py` if it needs a new look, and register it in
`bot.py`.

## Setup

1. **Create a Discord application and bot:**
   - Go to <https://discord.com/developers/applications> → **New
     Application**.
   - Open the **Bot** tab → **Reset Token** → copy it (this is
     `DISCORD_TOKEN`).
   - Under **Installation** (or **OAuth2 → URL Generator**), select the
     `bot` and `applications.commands` scopes, then the `Send Messages`
     and `Use Slash Commands` bot permissions, and use the generated URL
     to invite the bot to your server.

2. **Install dependencies:**

   ```bash
   cd discord_client
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv/Scripts/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Then edit `.env`:

   | Variable            | Required | Description                                                                 |
   |---------------------|----------|-------------------------------------------------------------------------------|
   | `DISCORD_TOKEN`     | yes      | Your bot's token from the Discord Developer Portal.                          |
   | `BACKEND_URL`       | yes      | Base URL of the running FastAPI backend, e.g. `http://localhost:8000`.       |
   | `DISCORD_GUILD_ID`  | no       | Server ID to sync commands to instantly during development. Omit for global sync (can take up to an hour to appear). |

4. **Make sure the backend is running** (see `../backend/README.md` or the
   project root README), then start the bot:

   ```bash
   python bot.py
   ```

   You should see `Logged in as <bot name>` and a log line confirming
   slash-command sync.

## Commands

| Command          | Calls                        | Shows                                                              |
|-------------------|-------------------------------|----------------------------------------------------------------------|
| `/status`         | `GET /devices`                | Every device, grouped by room, with on/off state.                    |
| `/power`          | `GET /power` (+`/power/summary`) | Current total power draw, energy used/predicted today, and an optional AI summary. |
| `/alerts`         | `GET /alerts`                  | All currently active alerts.                                          |
| `/room <room_id>` | `GET /rooms/{room_id}`         | A room's name and every device inside it.                             |
| `/analyze`        | `GET /office/summary`          | A Gemini-generated analysis of current office conditions (device status + power + alerts). |

`/status` groups devices by `room_id` because `GET /devices` doesn't
include room names -- use `/room <id>` to see the friendly name and full
detail for a specific room.

If the backend is unreachable or returns an error, the command replies
with a short warning instead of crashing or hanging -- the bot never
raises out of a command handler.

## Automatic alert notifications

When the backend's `AlertEngine` creates a **new** alert (not when one is
resolved), it runs its own pipeline entirely server-side:

```
Simulator → Device Service → Alert Engine → Alert Service → Gemini Service → Discord Service → Discord Channel
```

`Discord Service` (`backend/app/services/discord_service.py`) posts the
AI-generated message to a Discord channel via a **webhook** -- configured
with `DISCORD_WEBHOOK_URL` in the *backend's* `.env`, not this client's.
This bot has no code path involved in that flow at all: it neither sends
nor receives those notifications. If Discord or Gemini is unavailable, the
backend logs it and moves on -- it never fails a request because of it.

To receive these notifications:

1. In the target Discord channel, go to **Settings → Integrations →
   Webhooks → New Webhook**, copy its URL.
2. Set `DISCORD_WEBHOOK_URL` in `backend/.env` to that URL.
3. Restart the backend.

## Design constraints (recap)

- This client **never** accesses SQLite or any database directly.
- This client **never** contains business logic (alert thresholds, power
  calculations, etc.) -- all of that lives in the backend.
- Every command talks to the backend exclusively through its REST API.
- The backend keeps working even if this bot, Discord, or Gemini is down.
