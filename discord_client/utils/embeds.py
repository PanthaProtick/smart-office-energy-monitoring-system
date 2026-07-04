"""Discord embed formatting helpers.

Per Milestone 11's design constraints, formatting must be isolated from
command handlers: every command in `commands/` fetches data via
`services.backend_client.BackendClient` and hands it straight to one of
these functions. None of these functions make network calls or contain
business logic -- they only turn already-fetched backend data into a
`discord.Embed`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord

COLOR_STATUS = 0x3498DB
COLOR_POWER = 0xF1C40F
COLOR_ALERT = 0xE74C3C
COLOR_ROOM = 0x2ECC71
COLOR_ANALYSIS = 0x9B59B6


def _finalize(embed: discord.Embed) -> discord.Embed:
    """Shared footer/timestamp applied to every embed this module builds."""
    embed.set_footer(text="Smart Office Energy Monitoring")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def create_status_embed(devices: list[dict]) -> discord.Embed:
    """Group /devices results by room and show each device's on/off state.

    GET /devices doesn't include room names (only room_id), so rooms are
    labeled by ID here. Use /room <id> to see a specific room's name and
    full device list.
    """
    embed = discord.Embed(title="🏢 Office Status", color=COLOR_STATUS)

    if not devices:
        embed.description = "No devices found."
        return _finalize(embed)

    by_room: dict[int, list[dict]] = {}
    for device in devices:
        by_room.setdefault(device.get("room_id"), []).append(device)

    total_active = sum(1 for d in devices if d.get("is_active"))
    embed.description = f"{total_active}/{len(devices)} device(s) active across {len(by_room)} room(s)."

    for room_id in sorted(by_room, key=lambda r: (r is None, r)):
        room_devices = by_room[room_id]
        active_count = sum(1 for d in room_devices if d.get("is_active"))
        lines = [
            f"{'🟢' if d.get('is_active') else '⚪'} {d.get('name')} "
            f"({d.get('type')}, {d.get('power_rating')}W)"
            for d in room_devices
        ]
        embed.add_field(
            name=f"Room {room_id} ({active_count}/{len(room_devices)} active)",
            value="\n".join(lines),
            inline=False,
        )

    return _finalize(embed)


def create_power_embed(power_data: dict) -> discord.Embed:
    """Show current total power draw, energy usage, and an optional AI summary."""
    embed = discord.Embed(title="⚡ Power Usage", color=COLOR_POWER)

    total_power = power_data.get("total_power")
    usage_wh = power_data.get("total_power_usage_wh")
    predicted_wh = power_data.get("predicted_power_usage_wh")

    if total_power is not None:
        embed.add_field(name="Current Total Power", value=f"{total_power:.1f} W", inline=True)
    if usage_wh is not None:
        embed.add_field(name="Used Today", value=f"{usage_wh:.1f} Wh", inline=True)
    if predicted_wh is not None:
        embed.add_field(name="Predicted Today", value=f"{predicted_wh:.1f} Wh", inline=True)

    ai_summary = power_data.get("ai_summary")
    if ai_summary:
        embed.add_field(name="AI Summary", value=ai_summary, inline=False)

    return _finalize(embed)


def create_alert_embed(alerts: list[dict]) -> discord.Embed:
    """Show all currently active alerts."""
    embed = discord.Embed(title="🚨 Active Alerts", color=COLOR_ALERT)

    if not alerts:
        embed.description = "No active alerts. Everything looks normal."
        return _finalize(embed)

    embed.description = f"{len(alerts)} active alert(s)."

    # Discord embeds cap at 25 fields -- truncate rather than error.
    for alert in alerts[:25]:
        label = str(alert.get("rule", "alert")).replace("_", " ").title()
        embed.add_field(
            name=f"{label} (#{alert.get('id')})",
            value=f"{alert.get('message')}\nTriggered: {alert.get('triggered_at')}",
            inline=False,
        )

    if len(alerts) > 25:
        embed.add_field(name="\u200b", value=f"...and {len(alerts) - 25} more.", inline=False)

    return _finalize(embed)


def create_room_embed(room_data: dict) -> discord.Embed:
    """Show a single room's name and every device inside it."""
    name = room_data.get("name", "Unknown Room")
    devices = room_data.get("devices", [])

    embed = discord.Embed(title=f"🚪 {name}", color=COLOR_ROOM)

    if not devices:
        embed.description = "No devices in this room."
        return _finalize(embed)

    active_count = sum(1 for d in devices if d.get("is_active"))
    embed.description = f"{active_count}/{len(devices)} device(s) active."

    for d in devices:
        state = "🟢 On" if d.get("is_active") else "⚪ Off"
        embed.add_field(
            name=d.get("name", "Device"),
            value=f"{state} — {d.get('type')} — {d.get('power_rating')}W",
            inline=True,
        )

    return _finalize(embed)


def create_analysis_embed(analysis_data: dict) -> discord.Embed:
    """Show the combined office-wide snapshot plus its Gemini-generated analysis."""
    embed = discord.Embed(title="🧠 Office Analysis", color=COLOR_ANALYSIS)

    total_power = analysis_data.get("total_power")
    active_devices = analysis_data.get("active_devices")
    total_devices = analysis_data.get("total_devices")
    active_rooms = analysis_data.get("active_rooms")
    total_rooms = analysis_data.get("total_rooms")
    active_alerts = analysis_data.get("active_alerts")

    if total_power is not None:
        embed.add_field(name="Total Power", value=f"{total_power:.1f} W", inline=True)
    if active_devices is not None and total_devices is not None:
        embed.add_field(name="Devices Active", value=f"{active_devices}/{total_devices}", inline=True)
    if active_rooms is not None and total_rooms is not None:
        embed.add_field(name="Rooms Fully Active", value=f"{active_rooms}/{total_rooms}", inline=True)
    if active_alerts is not None:
        embed.add_field(name="Active Alerts", value=str(active_alerts), inline=True)

    ai_summary = analysis_data.get("ai_summary")
    if ai_summary:
        embed.add_field(name="AI Analysis", value=ai_summary, inline=False)

    return _finalize(embed)
