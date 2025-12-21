# cogs/writeup_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional
from datetime import datetime

from utils import database

# --- Constants ---
CYBER_THEME_COLOR = 0x00FFFF

# Common CTF categories
CTF_CATEGORIES = [
    "Web",
    "Pwn",
    "Reverse",
    "Crypto",
    "Forensics",
    "Misc",
    "OSINT",
    "Steganography",
    "Mobile",
    "Hardware",
    "Blockchain",
    "Cloud",
    "AI/ML",
    "Game Hacking",
]


class WriteupCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.logger.info("WriteupCommands Cog initialized.")

    async def event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for event names (includes past events)."""
        user_events = await database.get_user_events(interaction.user.id, include_past=True)
        choices = []
        for event in user_events:
            if current.lower() in event["event_name"].lower():
                display_name = event["event_name"][:99]
                choices.append(
                    app_commands.Choice(name=display_name, value=event["event_name"])
                )
            if len(choices) >= 25:
                break
        return choices

    async def category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for CTF categories."""
        current_lower = current.lower()
        choices = [
            app_commands.Choice(name=cat, value=cat)
            for cat in CTF_CATEGORIES
            if current_lower in cat.lower()
        ]
        return choices[:25]

    # --- Add Writeup ---
    @app_commands.command(
        name="writeup",
        description="Add a writeup link to an event."
    )
    @app_commands.describe(
        event_name="The event to add the writeup to",
        url="URL to the writeup (blog, GitHub, CTFtime, etc.)",
        challenge_name="Name of the challenge (optional)",
        category="Category of the challenge (Web, Pwn, etc.)",
        title="Title for this writeup (optional)",
        notes="Additional notes (optional)"
    )
    async def add_writeup(
        self,
        interaction: discord.Interaction,
        event_name: str,
        url: str,
        challenge_name: Optional[str] = None,
        category: Optional[str] = None,
        title: Optional[str] = None,
        notes: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        # Validate URL
        if not url.startswith(("http://", "https://")):
            await interaction.followup.send(
                "Invalid URL. Please provide a valid URL starting with http:// or https://",
                ephemeral=True
            )
            return

        # Get event
        event = await database.get_event_by_name(event_name)
        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found.",
                ephemeral=True
            )
            return

        # Add writeup
        writeup_id = await database.add_writeup(
            event_id=event["id"],
            user_id=interaction.user.id,
            url=url,
            title=title,
            challenge_name=challenge_name,
            category=category,
            notes=notes
        )

        embed = discord.Embed(
            title="📝 Writeup Added",
            description=f"Successfully added writeup for **{event_name}**",
            color=CYBER_THEME_COLOR,
        )

        if challenge_name:
            embed.add_field(name="Challenge", value=challenge_name, inline=True)
        if category:
            embed.add_field(name="Category", value=category, inline=True)
        if title:
            embed.add_field(name="Title", value=title, inline=True)

        embed.add_field(name="URL", value=url, inline=False)

        if notes:
            embed.add_field(name="Notes", value=notes[:200], inline=False)

        embed.set_footer(text=f"Writeup ID: {writeup_id}")

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"User {interaction.user.id} added writeup for event {event_name}")

    @add_writeup.autocomplete("event_name")
    async def writeup_event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.event_autocomplete(interaction, current)

    @add_writeup.autocomplete("category")
    async def writeup_category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.category_autocomplete(interaction, current)

    # --- List Writeups for Event ---
    @app_commands.command(
        name="writeups",
        description="View writeups for an event."
    )
    @app_commands.describe(
        event_name="The event to view writeups for"
    )
    async def list_event_writeups(
        self,
        interaction: discord.Interaction,
        event_name: str
    ):
        await interaction.response.defer(ephemeral=True)

        event = await database.get_event_by_name(event_name)
        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found.",
                ephemeral=True
            )
            return

        writeups = await database.get_event_writeups(event["id"])

        if not writeups:
            await interaction.followup.send(
                f"No writeups found for **{event_name}**.\n\nUse `/writeup` to add one!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📝 Writeups for {event_name}",
            description=f"Found {len(writeups)} writeup(s):",
            color=CYBER_THEME_COLOR,
        )

        for w in writeups[:10]:
            # Build title
            display_title = w.get("title") or w.get("challenge_name") or "Writeup"
            if w.get("category"):
                display_title = f"[{w['category']}] {display_title}"

            # Build value
            value_parts = [f"[Link]({w['url']})"]
            if w.get("notes"):
                value_parts.append(f"\n_{w['notes'][:100]}_")

            # Get author
            try:
                author = await self.bot.fetch_user(w["user_id"])
                value_parts.append(f"\n*by {author.display_name}*")
            except:
                pass

            embed.add_field(
                name=display_title,
                value=" ".join(value_parts),
                inline=False
            )

        if len(writeups) > 10:
            embed.set_footer(text=f"Showing 10 of {len(writeups)} writeups")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @list_event_writeups.autocomplete("event_name")
    async def list_writeups_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.event_autocomplete(interaction, current)

    # --- My Writeups ---
    @app_commands.command(
        name="my_writeups",
        description="View all your writeups."
    )
    @app_commands.describe(
        limit="Maximum number of writeups to show (default: 20)"
    )
    async def my_writeups(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 50] = 20
    ):
        await interaction.response.defer(ephemeral=True)

        writeups = await database.get_user_writeups(interaction.user.id, limit=limit)

        if not writeups:
            await interaction.followup.send(
                "You haven't added any writeups yet.\n\nUse `/writeup` after completing a CTF!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📝 Your Writeups",
            description=f"Found {len(writeups)} writeup(s):",
            color=CYBER_THEME_COLOR,
        )

        for w in writeups[:15]:
            # Build title
            display_title = w.get("title") or w.get("challenge_name") or "Writeup"
            event_title = w.get("event_title") or w.get("event_name", "Unknown Event")

            # Build value
            value = f"**Event:** {event_title}\n[View Writeup]({w['url']})"
            if w.get("category"):
                value = f"**Category:** {w['category']}\n" + value

            embed.add_field(
                name=display_title,
                value=value,
                inline=False
            )

        if len(writeups) > 15:
            embed.set_footer(text=f"Showing 15 of {len(writeups)} writeups")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Delete Writeup ---
    @app_commands.command(
        name="writeup_delete",
        description="Delete one of your writeups."
    )
    @app_commands.describe(
        writeup_id="The ID of the writeup to delete (shown in writeup footer)"
    )
    async def delete_writeup(
        self,
        interaction: discord.Interaction,
        writeup_id: int
    ):
        await interaction.response.defer(ephemeral=True)

        success = await database.remove_writeup(writeup_id, interaction.user.id)

        if success:
            await interaction.followup.send(
                f"✅ Writeup #{writeup_id} has been deleted.",
                ephemeral=True
            )
            self.logger.info(f"User {interaction.user.id} deleted writeup {writeup_id}")
        else:
            await interaction.followup.send(
                f"Could not delete writeup #{writeup_id}. Make sure it exists and belongs to you.",
                ephemeral=True
            )


# --- Setup Function ---
async def setup(bot: commands.Bot):
    await bot.add_cog(WriteupCommands(bot))
