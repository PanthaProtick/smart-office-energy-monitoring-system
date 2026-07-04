"""/analyze -- calls the backend's combined analysis endpoint.

The backend gathers device status, current power, and active alerts, then
runs GeminiService.generate_office_analysis() over that snapshot
(app/apis/summary.py's GET /office/summary). This command simply displays
the returned summary -- no analysis happens client-side.
"""

import logging

import discord

from services.backend_client import BackendError
from utils.embeds import create_analysis_embed

logger = logging.getLogger("discord_client.commands.analyze")


def register(bot):
    @bot.tree.command(
        name="analyze", description="Get an AI-generated analysis of current office conditions"
    )
    async def analyze(interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            data = await bot.backend.get_analysis()
        except BackendError as exc:
            logger.warning("analyze command failed: %s", exc)
            await interaction.followup.send(f"⚠️ Could not reach the backend: {exc}")
            return

        await interaction.followup.send(embed=create_analysis_embed(data))
