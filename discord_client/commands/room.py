"""/room -- calls GET /rooms/{room_id} and displays all devices in that room."""

import logging

import discord

from services.backend_client import BackendError
from utils.embeds import create_room_embed

logger = logging.getLogger("discord_client.commands.room")


def register(bot):
    @bot.tree.command(name="room", description="Show all devices within a specific room")
    @discord.app_commands.describe(room_id="The room's numeric ID (see /status for room IDs)")
    async def room(interaction: discord.Interaction, room_id: int):
        await interaction.response.defer()

        try:
            data = await bot.backend.get_room(room_id)
        except BackendError as exc:
            logger.warning("room command failed for room_id=%s: %s", room_id, exc)
            await interaction.followup.send(f"⚠️ Could not find room {room_id}: {exc}")
            return

        await interaction.followup.send(embed=create_room_embed(data))
