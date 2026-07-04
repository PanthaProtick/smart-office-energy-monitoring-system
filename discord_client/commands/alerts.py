"""/alerts -- calls GET /alerts and displays all active alerts."""

import logging

import discord

from services.backend_client import BackendError
from utils.embeds import create_alert_embed

logger = logging.getLogger("discord_client.commands.alerts")


def register(bot):
    @bot.tree.command(name="alerts", description="Show all active alerts")
    async def alerts(interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            data = await bot.backend.get_alerts()
        except BackendError as exc:
            logger.warning("alerts command failed: %s", exc)
            await interaction.followup.send(f"⚠️ Could not reach the backend: {exc}")
            return

        await interaction.followup.send(embed=create_alert_embed(data))
