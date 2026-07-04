"""Discord bot entrypoint.

Per Milestone 11's design constraints, this file (and everything else in
this package) contains no business logic: it only wires together the
slash commands defined in `commands/`, each of which calls the FastAPI
backend through `services.backend_client.BackendClient` and renders the
result with a helper from `utils.embeds`. All device/alert/power state and
every decision about what counts as "worth alerting on" lives in the
backend -- this bot never touches SQLite and never talks to Gemini
directly.

Run with:

    cd discord_client
    pip install -r requirements.txt
    cp .env.example .env  # then fill in DISCORD_TOKEN
    python bot.py
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config import DISCORD_GUILD_ID, DISCORD_TOKEN
from services.backend_client import BackendClient
from commands import alerts, analyze, power, room, status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("discord_client.bot")

# Slash commands don't need privileged intents (message content, members,
# etc.) -- the default intent set is enough.
INTENTS = discord.Intents.default()

# Every command module exposes a single register(bot) function that
# attaches its slash command to bot.tree. Adding a new command later is
# just: create commands/<name>.py with a register(bot), import it here,
# and add it to this tuple.
COMMAND_MODULES = (status, power, alerts, room, analyze)


class OfficeBot(commands.Bot):
    """Standalone Discord client for the Smart Office Energy Monitoring backend."""

    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        # One shared BackendClient (and one shared httpx connection pool)
        # for the whole process -- commands reach it via bot.backend.
        self.backend = BackendClient()

    async def setup_hook(self):
        for module in COMMAND_MODULES:
            module.register(self)

        if DISCORD_GUILD_ID is not None:
            # Guild-scoped sync propagates almost instantly -- much nicer
            # for local development than waiting up to an hour for a
            # global sync.
            guild = discord.Object(id=DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced slash commands to guild %s", DISCORD_GUILD_ID)
        else:
            await self.tree.sync()
            logger.info("Synced slash commands globally (can take up to an hour to appear)")

    async def on_ready(self):
        logger.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))

    async def close(self):
        # Always release the backend's connection pool, even on a crash
        # during shutdown -- a leaked httpx client keeps sockets open.
        await self.backend.close()
        await super().close()


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Copy discord_client/.env.example to "
            "discord_client/.env and fill in your bot token."
        )
    bot = OfficeBot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
