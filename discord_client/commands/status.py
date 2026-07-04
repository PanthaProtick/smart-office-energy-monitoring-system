"""/status -- calls GET /devices and displays all rooms and devices grouped by room."""

import logging

import discord

from services.backend_client import BackendError
from utils.embeds import create_status_embed

logger = logging.getLogger("discord_client.commands.status")


def register(bot):
    @bot.tree.command(name="status", description="Show all rooms and devices, grouped by room")
    async def status(interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            devices = await bot.backend.get_devices()
        except BackendError as exc:
            logger.warning("status command failed: %s", exc)
            await interaction.followup.send(f"⚠️ Could not reach the backend: {exc}")
            return

        await interaction.followup.send(embed=create_status_embed(devices))
