"""Environment configuration for the standalone Discord client.

Everything the client needs to run lives in a handful of environment
variables (see .env.example). Nothing here talks to Discord, the backend,
or SQLite -- this module only reads configuration.
"""

import os

from dotenv import load_dotenv

# Loads a local .env file if present (no-op if it doesn't exist or the
# variable is already set in the real environment -- e.g. in production).
load_dotenv()

# Discord bot token, from https://discord.com/developers/applications.
# Required to log in at all.
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")

# Base URL of the running FastAPI backend. The client never talks to
# anything else -- no SQLite, no direct Gemini calls.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")

# How long to wait for a single backend REST call before giving up.
REQUEST_TIMEOUT_S = float(os.environ.get("BACKEND_REQUEST_TIMEOUT_S", "10"))

# Optional: restrict slash-command sync to one guild (server) for near-
# instant updates during development. Global command sync can take up to
# an hour to propagate to every server, which makes iterating painful.
# Leave unset to sync commands globally.
_guild_id_raw = os.environ.get("DISCORD_GUILD_ID", "").strip()
DISCORD_GUILD_ID = int(_guild_id_raw) if _guild_id_raw else None
