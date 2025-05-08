# cogs/general_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timedelta
import pytz
from textwrap import dedent 

from utils import ctftime_api

# --- Constants & Configuration ---
CYBER_THEME_COLOR = 0x00FFFF  # Cyan/Aqua - consistent with event_commands


# Helper from event_commands (could be moved to a shared utils file)
def format_datetime_utc(dt: datetime):
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)  # Assume UTC if no timezone
    else:
        dt = dt.astimezone(pytz.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


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
        limit="How many upcoming events to show (default: 10, max: 25)"
    )
    async def upcoming_events(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
    ):
        await interaction.response.defer()  # Public response okay here
        self.logger.info(
            f"User {interaction.user.id} requested {limit} upcoming events."
        )

        upcoming_list = ctftime_api.fetch_upcoming_events(limit=limit)

        if not upcoming_list:
            await interaction.followup.send(
                "Could not fetch upcoming events from CTFtime. The API might be down or there are no upcoming events."
            )
            return

        embed = discord.Embed(
            title="📅 Upcoming CTF Events (from CTFtime)",
            description=f"Here are the next {len(upcoming_list)} upcoming CTF events:",
            color=CYBER_THEME_COLOR,
        )

        for event in upcoming_list:
            event_name = event.get("title", "N/A")
            event_weight = event.get("weight", "N/A")
            official_url = event.get("url", "Not available")
            ctftime_url = event.get("ctftime_url", "Not available")
            start_dt = event.get("start_dt")
            end_dt = event.get("finish_dt")

            value_lines = []
            if start_dt and end_dt:
                value_lines.append(f"**Start:** {format_datetime_utc(start_dt)}")
                value_lines.append(f"**End:**   {format_datetime_utc(end_dt)}")
            value_lines.append(f"**Weight:** {event_weight}")
            links = []
            if ctftime_url != "Not available":
                links.append(f"[CTFtime]({ctftime_url})")
            if official_url != "Not available":
                links.append(f"[Official Site]({official_url})")
            if links:
                value_lines.append(" | ".join(links))

            embed.add_field(
                name=f"🛡️ {event_name}", value="\n".join(value_lines), inline=False
            )

        embed.set_footer(
            text=f"Source: CTFtime.org | Use /add <url> to add an event to your agenda."
        )
        await interaction.followup.send(embed=embed)

    # --- Slash Command: CTF Info (Placeholder/Example) ---
    # This is a basic example, the AI integration is a stretch goal
    @app_commands.command(
        name="ctf_info",
        description="(Experimental) Tries to find info about a CTF by name/URL.",
    )
    @app_commands.describe(query="The name or CTFtime URL of the CTF.")
    async def ctf_info(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(
            f"User {interaction.user.id} requested info for query: {query}"
        )

        # Basic placeholder - just echoes the query for now
        # TODO: Implement actual lookup logic (e.g., search CTFtime, potentially use AI later)
        embed = discord.Embed(
            title="🚧 CTF Info (Experimental)",
            description=f"Looking up info for: `{query}`\n\n_(This feature is under development. Currently, it only confirms the query.)_",
            color=0xFFA500,  # Orange for experimental
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="help", description="Shows all slash commands and what they do."
    )
    async def slash_help(self, interaction: discord.Interaction):
        help_text = dedent(
            """
            **CTF Notifier – Slash Commands**

            `/add <ctftime_url>` – Add an event to your agenda  
            `/agenda` – Show all events you saved  
            `/details <event_name>` – Full info about one event  
            `/remove <event_name>` – Delete one event  
            `/clear` – Wipe your whole agenda  

            `/upcoming [limit]` – Next events on CTFtime  
            `/ctf_info <query>` – Experimental CTF lookup  

            _Tip: start typing `/` and Discord will autocomplete._
        """
        )

        embed = discord.Embed(description=help_text, color=0x00FFFF)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Setup Function --- #
async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCommands(bot))
