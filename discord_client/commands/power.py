"""/power -- calls GET /power and displays current total power plus an
optional AI summary from the backend."""

import logging

import discord

from services.backend_client import BackendError
from utils.embeds import create_power_embed

logger = logging.getLogger("discord_client.commands.power")


def register(bot):
    @bot.tree.command(name="power", description="Show current power draw and an AI summary")
    async def power(interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            data = await bot.backend.get_power()
        except BackendError as exc:
            logger.warning("power command failed: %s", exc)
            await interaction.followup.send(f"⚠️ Could not reach the backend: {exc}")
            return

        await interaction.followup.send(embed=create_power_embed(data))
