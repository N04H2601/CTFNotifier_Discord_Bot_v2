# cogs/general_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from typing import Optional
import pytz
from textwrap import dedent

from utils import ctftime_api, database, helpers

# --- Constants & Configuration ---
CYBER_THEME_COLOR = 0x00FFFF  # Cyan/Aqua

# Format choices for filtering
FORMAT_CHOICES = [
    app_commands.Choice(name="Jeopardy", value="Jeopardy"),
    app_commands.Choice(name="Attack-Defense", value="Attack-Defense"),
    app_commands.Choice(name="Hack Quest", value="Hack quest"),
]


class GeneralCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.logger.info("GeneralCommands Cog initialized.")

    # --- Slash Command: Upcoming Events ---
    @app_commands.command(
        name="upcoming", description="Shows upcoming CTF events from CTFtime."
    )
    @app_commands.describe(
        limit="How many upcoming events to show (default: 10, max: 25)",
        format="Filter by event format",
        min_weight="Minimum CTF weight (0-100)"
    )
    @app_commands.choices(format=FORMAT_CHOICES)
    async def upcoming_events(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
        format: Optional[str] = None,
        min_weight: Optional[app_commands.Range[float, 0, 100]] = None
    ):
        await interaction.response.defer()
        self.logger.info(
            f"User {interaction.user.id} requested {limit} upcoming events (format={format}, min_weight={min_weight})"
        )

        upcoming_list = await ctftime_api.fetch_upcoming_events(
            limit=limit,
            format_filter=format,
            min_weight=min_weight
        )

        if not upcoming_list:
            message = "Could not fetch upcoming events from CTFtime."
            if format or min_weight:
                message += " Try removing filters or check back later."
            await interaction.followup.send(message)
            return

        # Build title with filters
        title_parts = ["📅 Upcoming CTF Events"]
        if format:
            title_parts.append(f"[{format}]")
        if min_weight:
            title_parts.append(f"[Weight ≥ {min_weight}]")

        embed = discord.Embed(
            title=" ".join(title_parts),
            description=f"Found {len(upcoming_list)} event(s) from CTFtime:",
            color=CYBER_THEME_COLOR,
        )

        for event in upcoming_list:
            event_name = event.get("title", "N/A")
            event_weight = event.get("weight", 0)
            official_url = event.get("url", "")
            ctftime_url = event.get("ctftime_url", "")
            start_dt = event.get("start_dt")
            end_dt = event.get("finish_dt")
            event_format = event.get("format", "N/A")

            # Build field value
            value_lines = []
            if start_dt:
                value_lines.append(f"**Start:** {helpers.format_discord_timestamp(start_dt, 'R')}")
            if end_dt:
                duration = helpers.calculate_duration(start_dt, end_dt)
                value_lines.append(f"**Duration:** {duration}")

            value_lines.append(f"**Format:** {event_format}")
            value_lines.append(f"**Weight:** {helpers.format_weight(event_weight)}")

            # Links
            links = []
            if ctftime_url:
                links.append(f"[CTFtime]({ctftime_url})")
            if official_url:
                links.append(f"[Site]({official_url})")
            if links:
                value_lines.append(" | ".join(links))

            embed.add_field(
                name=f"🛡️ {event_name}",
                value="\n".join(value_lines),
                inline=False
            )

        embed.set_footer(
            text="Source: CTFtime.org | Use /add <url> to add to your agenda"
        )
        await interaction.followup.send(embed=embed)

    # --- Slash Command: User Statistics ---
    @app_commands.command(
        name="stats",
        description="View your CTF participation statistics."
    )
    async def user_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        stats = await database.get_user_stats(interaction.user.id)

        embed = discord.Embed(
            title=f"📊 CTF Stats for {interaction.user.display_name}",
            color=CYBER_THEME_COLOR,
        )

        # Main stats
        embed.add_field(
            name="📅 Events",
            value=(
                f"**Total:** {stats['total_events']}\n"
                f"**Completed:** {stats['past_events']}\n"
                f"**Upcoming:** {stats['upcoming_events']}\n"
                f"**In Progress:** {stats['current_events']}"
            ),
            inline=True
        )

        embed.add_field(
            name="📝 Writeups",
            value=f"**Total:** {stats['total_writeups']}",
            inline=True
        )

        embed.add_field(
            name="⚖️ Average Weight",
            value=f"**{stats['average_weight']:.2f}**" if stats['average_weight'] > 0 else "N/A",
            inline=True
        )

        # Format breakdown
        if stats['format_stats']:
            format_text = "\n".join([
                f"• **{fmt}:** {count}"
                for fmt, count in sorted(stats['format_stats'].items(), key=lambda x: -x[1])
            ])
            embed.add_field(
                name="🎯 Events by Format",
                value=format_text,
                inline=False
            )

        # Recent activity
        past_events = await database.get_user_past_events(interaction.user.id, limit=5)
        if past_events:
            recent_text = "\n".join([
                f"• {e['event_name']}"
                for e in past_events[:5]
            ])
            embed.add_field(
                name="🏆 Recent CTFs",
                value=recent_text,
                inline=False
            )

        embed.set_footer(text="Keep playing CTFs to improve your stats!")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: History ---
    @app_commands.command(
        name="history",
        description="View your past CTF events."
    )
    @app_commands.describe(
        limit="Number of past events to show (default: 10)"
    )
    async def history(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 50] = 10
    ):
        await interaction.response.defer(ephemeral=True)

        past_events = await database.get_user_past_events(interaction.user.id, limit=limit)

        if not past_events:
            await interaction.followup.send(
                "You don't have any completed CTFs yet. Participate in some events!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🏆 CTF History for {interaction.user.display_name}",
            description=f"Your last {len(past_events)} completed CTF(s):",
            color=CYBER_THEME_COLOR,
        )

        for event in past_events:
            end_dt = event["end_time"]
            if isinstance(end_dt, str):
                end_dt = datetime.fromisoformat(end_dt)

            # Get writeups count for this event
            writeups = await database.get_event_writeups(event["id"])
            writeup_text = f" | 📝 {len(writeups)} writeup(s)" if writeups else ""

            embed.add_field(
                name=f"🛡️ {event['event_name']}",
                value=(
                    f"**Ended:** {helpers.format_discord_timestamp(end_dt, 'R')}\n"
                    f"**Format:** {event.get('format', 'N/A')}{writeup_text}"
                ),
                inline=False
            )

        embed.set_footer(text="Use /writeup to add writeups for these events")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: CTF Info (Placeholder) ---
    @app_commands.command(
        name="ctf_info",
        description="(Experimental) Search for CTF info by name."
    )
    @app_commands.describe(query="The name of the CTF to search for")
    async def ctf_info(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(f"User {interaction.user.id} searched for: {query}")

        # Search upcoming events
        results = await ctftime_api.search_events(query, limit=5)

        if not results:
            embed = discord.Embed(
                title="🔍 CTF Search",
                description=f"No upcoming CTFs found matching: `{query}`\n\n*Note: This only searches upcoming events on CTFtime.*",
                color=0xFFA500,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔍 Search Results for '{query}'",
            description=f"Found {len(results)} matching CTF(s):",
            color=CYBER_THEME_COLOR,
        )

        for event in results:
            start_dt = event.get("start_dt")
            ctftime_url = event.get("ctftime_url", "")

            value = f"**Start:** {helpers.format_discord_timestamp(start_dt, 'R')}"
            if ctftime_url:
                value += f"\n[View on CTFtime]({ctftime_url})"

            embed.add_field(
                name=f"🛡️ {event['title']}",
                value=value,
                inline=False
            )

        embed.set_footer(text="Use /add <ctftime_url> to add to your agenda")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: Help ---
    @app_commands.command(
        name="help", description="Shows all available commands and how to use them."
    )
    async def slash_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 CTF Notifier - Command Guide",
            description="Your personal CTF event manager and notification bot!",
            color=CYBER_THEME_COLOR,
        )

        # Event Management
        embed.add_field(
            name="📅 Event Management",
            value=(
                "`/add <url>` - Add CTFtime event\n"
                "`/add_custom` - Create custom event\n"
                "`/agenda` - View your events\n"
                "`/details <event>` - Event details\n"
                "`/remove <event>` - Remove event\n"
                "`/clear` - Clear all events\n"
                "`/search <query>` - Search your events"
            ),
            inline=True,
        )

        # Team Features
        embed.add_field(
            name="👥 Team Features",
            value=(
                "`/team <event>` - View team\n"
                "`/team_add` - Add teammate\n"
                "`/team_remove` - Remove teammate"
            ),
            inline=True,
        )

        # Discovery
        embed.add_field(
            name="🔍 Discover CTFs",
            value=(
                "`/upcoming` - Upcoming CTFs\n"
                "`/ctf_info <query>` - Search CTFs\n"
                "`/history` - Your past CTFs\n"
                "`/stats` - Your statistics"
            ),
            inline=True,
        )

        # Writeups
        embed.add_field(
            name="📝 Writeups",
            value=(
                "`/writeup` - Add writeup\n"
                "`/writeups <event>` - Event writeups\n"
                "`/my_writeups` - Your writeups\n"
                "`/writeup_delete` - Delete writeup"
            ),
            inline=True,
        )

        # Settings
        embed.add_field(
            name="⚙️ Settings",
            value=(
                "`/settings` - View settings\n"
                "`/timezone` - Set timezone\n"
                "`/notifications` - Configure alerts\n"
                "`/calendar` - Export to iCal"
            ),
            inline=True,
        )

        # Admin
        embed.add_field(
            name="🔧 Server Admin",
            value=(
                "`/set_channel` - Set notification channel\n"
                "`/remove_channel` - Disable channel notifs"
            ),
            inline=True,
        )

        embed.set_footer(text="Tip: Start typing / and Discord will show available commands!")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Setup Function ---
async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCommands(bot))
