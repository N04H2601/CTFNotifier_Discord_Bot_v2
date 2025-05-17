# cogs/event_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timedelta
import pytz
import re

from utils import database, ctftime_api, helpers

# --- Constants & Configuration ---
CYBER_THEME_COLOR = 0x00FFFF  # Cyan/Aqua - can be adjusted
CTFTIME_EVENT_URL_REGEX = r"https?://ctftime.org/event/(\d+)"


class EventCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.logger.info("EventCommands Cog initialized.")

    # --- Slash Command: Add Event ---
    @app_commands.command(
        name="add",
        description="Adds a CTF event to your personal agenda using its CTFtime URL.",
    )
    @app_commands.describe(
        ctftime_url="The full URL of the event on CTFtime (e.g., https://ctftime.org/event/1234)"
    )
    async def add_event(self, interaction: discord.Interaction, ctftime_url: str):
        await interaction.response.defer(
            ephemeral=True
        )  # Acknowledge interaction, work in background

        match = re.match(CTFTIME_EVENT_URL_REGEX, ctftime_url)
        if not match:
            await interaction.followup.send(
                "Invalid CTFtime event URL format. Please use a URL like `https://ctftime.org/event/1234`.",
                ephemeral=True,
            )
            return

        event_id = int(match.group(1))
        self.logger.info(
            f"User {interaction.user.id} attempting to add event ID: {event_id}"
        )

        event_data = ctftime_api.fetch_event_details(event_id)

        if not event_data:
            await interaction.followup.send(
                "Failed to fetch event details from CTFtime. The event might not exist or CTFtime API might be down.",
                ephemeral=True,
            )
            return

        # Check if event has already finished
        now_utc = datetime.now(pytz.utc)
        finish_time_utc = event_data["finish"].astimezone(pytz.utc)
        if finish_time_utc < now_utc:
            await interaction.followup.send(
                "This event has already finished and cannot be added.", ephemeral=True
            )
            return

        # Add event to user's database
        success = await database.add_event_to_user(interaction.user.id, event_data)

        if success:
            embed = discord.Embed(
                title="✅ Event Added",
                description=f"Successfully added **{event_data['event_name']}** to your personal agenda.",
                color=CYBER_THEME_COLOR,
            )
            embed.add_field(
                name="Start Time",
                value=helpers.format_discord_timestamp(event_data["start"]),
                inline=True,
            )
            embed.add_field(
                name="End Time",
                value=helpers.format_discord_timestamp(event_data["finish"]),
                inline=True,
            )
            embed.set_footer(text="Use /agenda to view your events.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.logger.info(
                f"Successfully added event 	{event_data['event_name']}	 for user {interaction.user.id}"
            )
        else:
            await interaction.followup.send(
                f"Event **{event_data['event_name']}** is already in your agenda.",
                ephemeral=True,
            )
            self.logger.warning(
                f"Event 	{event_data['event_name']}	 already exists for user {interaction.user.id}"
            )

    # --- Slash Command: Create Custom Event ---
    @app_commands.command(
        name="custom",
        description="Create a custom event in your personal agenda."
    )
    @app_commands.describe(
        name="Name of the event",
        start="Start time in YYYY-MM-DD HH:MM (UTC)",
        end="End time in YYYY-MM-DD HH:MM (UTC)",
        description="Optional description",
        url="Optional event URL"
    )
    async def create_custom_event(
        self,
        interaction: discord.Interaction,
        name: str,
        start: str,
        end: str,
        description: str | None = None,
        url: str | None = None,
    ):
        """Allows a user to create a custom event without CTFtime."""
        await interaction.response.defer(ephemeral=True)

        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            await interaction.followup.send(
                "Invalid date format. Use `YYYY-MM-DD HH:MM`.",
                ephemeral=True,
            )
            return

        if start_dt >= end_dt:
            await interaction.followup.send(
                "Start time must be before end time.", ephemeral=True
            )
            return

        event_data = {
            "event_name": name,
            "ctftime_url": None,
            "url": url,
            "start": start_dt,
            "finish": end_dt,
            "format": None,
            "organizers": None,
            "weight": None,
            "description": description,
            "participants": None,
        }

        success = await database.add_event_to_user(interaction.user.id, event_data)

        if success:
            embed = discord.Embed(
                title="✅ Custom Event Added",
                description=f"Successfully added **{name}** to your personal agenda.",
                color=CYBER_THEME_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                f"Event **{name}** is already in your agenda.", ephemeral=True
            )
    # --- Slash Command: View Agenda ---
    @app_commands.command(
        name="agenda", description="Displays your personal CTF event agenda."
    )
    async def view_agenda(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(f"User {interaction.user.id} requested their agenda.")

        user_events = await database.get_user_events(interaction.user.id)

        if not user_events:
            await interaction.followup.send(
                "Your agenda is empty. Use `/add` to add events!", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📅 {interaction.user.display_name}'s CTF Agenda",
            description="Here are the upcoming CTF events you've added:",
            color=CYBER_THEME_COLOR,
        )

        for event in user_events:
            # Ensure start and end times are datetime objects before formatting
            start_dt = event["start_time"]
            end_dt = event["end_time"]
            if isinstance(start_dt, str):
                start_dt = datetime.fromisoformat(start_dt)
            if isinstance(end_dt, str):
                end_dt = datetime.fromisoformat(end_dt)

            embed.add_field(
                name=f"🛡️ {event['event_name']}",
                value=f"**Start:** {helpers.format_discord_timestamp(start_dt)}\n**End:**   {helpers.format_discord_timestamp(end_dt)}",
                inline=False,
            )

        embed.set_footer(text="Use /details <event_name> for more info.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: Event Details ---
    @app_commands.command(
        name="details",
        description="Shows detailed information about an event in your agenda.",
    )
    @app_commands.describe(
        event_name="The exact name of the event (case-sensitive) from your /agenda."
    )
    async def event_details(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(
            f"User {interaction.user.id} requested details for event: {event_name}"
        )

        event = await database.get_event_details(interaction.user.id, event_name)

        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda. Check the name using `/agenda` (it's case-sensitive).",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"ℹ️ Event Details: {event['event_name']}",
            description=event.get("description", "No description available."),
            color=CYBER_THEME_COLOR,
        )

        # Ensure times are datetime objects
        start_dt = event["start_time"]
        end_dt = event["end_time"]
        if isinstance(start_dt, str):
            start_dt = datetime.fromisoformat(start_dt)
        if isinstance(end_dt, str):
            end_dt = datetime.fromisoformat(end_dt)

        embed.add_field(
            name="Start Time",
            value=helpers.format_discord_timestamp(start_dt),
            inline=True,
        )
        embed.add_field(
            name="End Time", value=helpers.format_discord_timestamp(end_dt), inline=True
        )
        embed.add_field(name="Format", value=event.get("format", "N/A"), inline=True)
        embed.add_field(
            name="Organizers", value=event.get("organizers", "N/A"), inline=True
        )
        embed.add_field(
            name="Weight", value=str(event.get("weight", "N/A")), inline=True
        )
        embed.add_field(
            name="Participants",
            value=str(event.get("participants", "N/A")),
            inline=True,
        )

        links = []
        if event.get("ctftime_url"):
            links.append(f"[CTFtime]({event['ctftime_url']})")
        if event.get("event_url"):
            links.append(f"[Official Site]({event['event_url']})")
        if links:
            embed.add_field(name="Links", value=" | ".join(links), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Autocomplete for Event Details/Remove ---
    async def event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        user_events = await database.get_user_events(interaction.user.id)
        choices = []
        for event in user_events:
            if current.lower() in event["event_name"].lower():
                # Truncate long names if necessary for display
                display_name = event["event_name"][:99]
                choices.append(
                    app_commands.Choice(name=display_name, value=event["event_name"])
                )
            if len(choices) >= 25:  # Discord limit
                break
        return choices

    @event_details.autocomplete("event_name")
    async def details_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.event_autocomplete(interaction, current)

    # --- Slash Command: Share Event ---
    @app_commands.command(
        name="share",
        description="Share one of your events with another user."
    )
    @app_commands.describe(
        event_name="Name of the event to share",
        user="User to share the event with"
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def share_event(
        self,
        interaction: discord.Interaction,
        event_name: str,
        user: discord.User
    ):
        await interaction.response.defer(ephemeral=True)

        event = await database.get_event_details(interaction.user.id, event_name)
        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda.", ephemeral=True
            )
            return

        event_data = {
            "event_name": event["event_name"],
            "ctftime_url": event.get("ctftime_url"),
            "url": event.get("event_url"),
            "start": event["start_time"],
            "finish": event["end_time"],
            "format": event.get("format"),
            "organizers": event.get("organizers"),
            "weight": event.get("weight"),
            "description": event.get("description"),
            "participants": event.get("participants"),
        }

        success = await database.add_event_to_user(user.id, event_data)
        if success:
            try:
                embed = discord.Embed(
                    title="📅 Event Shared",
                    description=f"{interaction.user.mention} shared **{event_name}** with you.",
                    color=CYBER_THEME_COLOR,
                )
                await user.send(embed=embed)
            except Exception:
                pass
            await interaction.followup.send(
                f"Shared **{event_name}** with {user.mention}.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"{user.mention} already has **{event_name}** in their agenda.",
                ephemeral=True,
            )
    @app_commands.command(
        name="remove", description="Removes an event from your personal agenda."
    )
    @app_commands.describe(
        event_name="The exact name of the event to remove (use autocomplete!)."
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def remove_event(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(
            f"User {interaction.user.id} attempting to remove event: {event_name}"
        )

        success = await database.remove_event_from_user(interaction.user.id, event_name)

        if success:
            await interaction.followup.send(
                f"🗑️ Event `{event_name}` removed from your agenda.", ephemeral=True
            )
            self.logger.info(
                f"Successfully removed event 	{event_name}	 for user {interaction.user.id}"
            )
        else:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda. Use `/agenda` to check the name.",
                ephemeral=True,
            )
            self.logger.warning(
                f"Attempted to remove non-existent event 	{event_name}	 for user {interaction.user.id}"
            )

    # --- Slash Command: Clear Agenda ---
    @app_commands.command(
        name="clear", description="Removes ALL events from your personal agenda."
    )
    async def clear_agenda(self, interaction: discord.Interaction):
        # Use a confirmation view
        view = ClearConfirmationView(interaction.user)
        embed = discord.Embed(
            title="⚠️ Confirm Clear Agenda",
            description="Are you sure you want to remove **ALL** events from your personal agenda? This action cannot be undone.",
            color=0xFFCC00,  # Warning Yellow
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        self.logger.info(
            f"User {interaction.user.id} initiated clear agenda confirmation."
        )
        # The view handles the actual clearing


# --- Confirmation View for Clear ---
class ClearConfirmationView(discord.ui.View):
    def __init__(self, author: discord.User, timeout=60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.logger = logging.getLogger(f"{__name__}.ClearConfirmationView")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the original command user to interact
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This confirmation is not for you.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        # Edit the original message to show timeout
        try:
            message = await self.message.edit(
                content="Confirmation timed out. Agenda was not cleared.",
                embed=None,
                view=None,
            )
        except discord.NotFound:
            pass  # Message might have been deleted
        self.logger.info(f"Clear confirmation timed out for user {self.author.id}")

    @discord.ui.button(
        label="Yes, Clear All",
        style=discord.ButtonStyle.danger,
        custom_id="confirm_clear",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        deleted_count = await database.clear_user_events(interaction.user.id)
        await interaction.response.edit_message(
            content=f"🗑️ Successfully cleared {deleted_count} events from your agenda.",
            embed=None,
            view=None,
        )
        self.logger.info(
            f"User {interaction.user.id} confirmed clearing agenda, removed {deleted_count} events."
        )
        self.stop()

    @discord.ui.button(
        label="No, Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="cancel_clear",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="❌ Agenda clearing cancelled.", embed=None, view=None
        )
        self.logger.info(f"User {interaction.user.id} cancelled clearing agenda.")
        self.stop()


# --- Setup Function --- #
async def setup(bot: commands.Bot):
    await bot.add_cog(EventCommands(bot))
