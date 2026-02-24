# cogs/event_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import pytz
import re

from utils import database, ctftime_api, helpers

# --- Constants & Configuration ---
CYBER_THEME_COLOR = 0x00FFFF  # Cyan/Aqua
CTFTIME_EVENT_URL_REGEX = r"https?://ctftime.org/event/(\d+)"


class EventCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.logger.info("EventCommands Cog initialized.")

    async def create_team_thread(
        self,
        interaction: discord.Interaction,
        event_name: str,
        event_data: dict,
        team_leader_id: int,
        teammate_ids: List[int],
    ) -> Optional[discord.Thread]:
        """Create a private thread for the team in the server's notification channel.

        Falls back to the channel where the command was invoked if no notification
        channel is configured.
        """
        if not interaction.guild:
            return None

        # Get the notification channel for this server
        server_settings = await database.get_server_settings(interaction.guild.id)
        channel_id = server_settings.get("notification_channel_id")

        channel = None
        if channel_id:
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                pass

        # Fall back to the interaction channel
        if not channel and interaction.channel:
            channel = interaction.channel

        if not channel or not hasattr(channel, 'create_thread'):
            return None

        try:
            # Create a private thread
            thread = await channel.create_thread(
                name=f"CTF - {event_name}",
                type=discord.ChannelType.private_thread,
                reason=f"CTF team thread for {event_name}",
            )

            # Add team leader and all teammates
            try:
                leader = interaction.guild.get_member(team_leader_id) or await interaction.guild.fetch_member(team_leader_id)
                if leader:
                    await thread.add_user(leader)
            except (discord.NotFound, discord.Forbidden):
                pass

            for tid in teammate_ids:
                try:
                    member = interaction.guild.get_member(tid) or await interaction.guild.fetch_member(tid)
                    if member:
                        await thread.add_user(member)
                except (discord.NotFound, discord.Forbidden):
                    self.logger.warning(f"Could not add user {tid} to thread for {event_name}")

            # Send welcome message with CTF info
            start = event_data.get("start") or event_data.get("start_time")
            finish = event_data.get("finish") or event_data.get("end_time")
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(finish, str):
                finish = datetime.fromisoformat(finish)

            welcome_embed = discord.Embed(
                title=f"🛡️ {event_data.get('title', event_name)}",
                description=(
                    f"Welcome to the team thread for **{event_name}**!\n\n"
                    f"This is your private space to coordinate, share resources, and discuss strategies."
                ),
                color=CYBER_THEME_COLOR,
            )

            if start:
                welcome_embed.add_field(
                    name="📅 Start",
                    value=f"{helpers.format_discord_timestamp(start, 'F')}\n{helpers.format_discord_timestamp(start, 'R')}",
                    inline=True,
                )
            if finish:
                welcome_embed.add_field(
                    name="🏁 End",
                    value=f"{helpers.format_discord_timestamp(finish, 'F')}\n{helpers.format_discord_timestamp(finish, 'R')}",
                    inline=True,
                )
            if start and finish:
                welcome_embed.add_field(
                    name="⏱️ Duration",
                    value=helpers.calculate_duration(start, finish),
                    inline=True,
                )

            event_format = event_data.get("format", "")
            if event_format:
                welcome_embed.add_field(name="🎯 Format", value=event_format, inline=True)

            # Links
            links = []
            ctftime_url = event_data.get("ctftime_url", "")
            official_url = event_data.get("url") or event_data.get("event_url", "")
            if ctftime_url:
                links.append(f"[CTFtime]({ctftime_url})")
            if official_url:
                links.append(f"[Official Site]({official_url})")
            if links:
                welcome_embed.add_field(name="🔗 Links", value=" | ".join(links), inline=False)

            # Team members
            all_members = [f"<@{team_leader_id}> (Team Leader)"]
            all_members += [f"<@{tid}>" for tid in teammate_ids]
            welcome_embed.add_field(
                name="👥 Team",
                value="\n".join(all_members),
                inline=False,
            )

            welcome_embed.set_footer(text="Good luck! Use /writeup to add writeups after the CTF.")
            await thread.send(embed=welcome_embed)

            self.logger.info(f"Created team thread for {event_name} with {len(teammate_ids)} teammates")
            return thread

        except discord.Forbidden:
            self.logger.warning(f"Cannot create thread in channel {channel.id} (no permission)")
            return None
        except Exception as e:
            self.logger.error(f"Error creating team thread: {e}", exc_info=True)
            return None

    # --- Slash Command: Add Event from CTFtime ---
    @app_commands.command(
        name="add",
        description="Adds a CTF event to your agenda using its CTFtime URL.",
    )
    @app_commands.describe(
        ctftime_url="The full URL of the event on CTFtime (e.g., https://ctftime.org/event/1234)",
        teammates="Tag teammates to add to this event (they'll receive notifications too)"
    )
    async def add_event(
        self,
        interaction: discord.Interaction,
        ctftime_url: str,
        teammates: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        match = re.match(CTFTIME_EVENT_URL_REGEX, ctftime_url)
        if not match:
            await interaction.followup.send(
                "Invalid CTFtime event URL format. Please use a URL like `https://ctftime.org/event/1234`.",
                ephemeral=True,
            )
            return

        event_id = int(match.group(1))
        self.logger.info(f"User {interaction.user.id} attempting to add event ID: {event_id}")

        event_data = await ctftime_api.fetch_event_details(event_id)

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

        # Add CTFtime ID for reference
        event_data["ctftime_id"] = event_id

        # Get server ID if in a guild
        server_id = interaction.guild.id if interaction.guild else None

        # Add event to user's database
        success = await database.add_event_to_user(
            interaction.user.id, event_data, server_id
        )

        if not success:
            await interaction.followup.send(
                f"Event **{event_data['event_name']}** is already in your agenda.",
                ephemeral=True,
            )
            return

        # Get event from DB to get the ID
        event = await database.get_event_by_name(event_data["event_name"])

        # Parse and add teammates if provided
        added_teammates = []
        if teammates and event:
            # Extract user mentions from the string
            mention_pattern = r"<@!?(\d+)>"
            mentioned_ids = re.findall(mention_pattern, teammates)

            for user_id_str in mentioned_ids:
                member_id = int(user_id_str)
                if member_id != interaction.user.id:
                    added = await database.add_event_member(
                        event["id"], interaction.user.id, member_id
                    )
                    if added:
                        added_teammates.append(member_id)

        # Build response embed
        embed = discord.Embed(
            title="✅ Event Added",
            description=f"Successfully added **{event_data['event_name']}** to your personal agenda.",
            color=CYBER_THEME_COLOR,
        )

        # Get user settings for timezone
        user_settings = await database.get_user_settings(interaction.user.id)
        user_tz = pytz.timezone(user_settings.get("timezone", "Europe/Paris"))

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

        if added_teammates:
            teammates_mentions = ", ".join([f"<@{uid}>" for uid in added_teammates])
            embed.add_field(
                name="👥 Teammates Added",
                value=teammates_mentions,
                inline=False,
            )

        embed.set_footer(text="Use /agenda to view your events • /calendar to export")

        # Create private thread for team if teammates were added
        thread = None
        if added_teammates and interaction.guild:
            thread = await self.create_team_thread(
                interaction, event_data["event_name"], event_data,
                interaction.user.id, added_teammates
            )
            if thread:
                embed.add_field(
                    name="💬 Team Thread",
                    value=f"Created: {thread.mention}",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Notify teammates via DM
        for teammate_id in added_teammates:
            try:
                user = await self.bot.fetch_user(teammate_id)
                dm_embed = discord.Embed(
                    title="📅 You've been added to a CTF!",
                    description=f"**{interaction.user.display_name}** added you to **{event_data['event_name']}**",
                    color=CYBER_THEME_COLOR,
                )
                dm_embed.add_field(
                    name="Start Time",
                    value=helpers.format_discord_timestamp(event_data["start"]),
                    inline=True,
                )
                dm_embed.add_field(
                    name="End Time",
                    value=helpers.format_discord_timestamp(event_data["finish"]),
                    inline=True,
                )
                if thread:
                    dm_embed.add_field(
                        name="💬 Team Thread",
                        value=f"Check the team thread in the server for coordination!",
                        inline=False,
                    )
                await user.send(embed=dm_embed)
            except (discord.Forbidden, discord.NotFound):
                pass

        self.logger.info(
            f"Successfully added event {event_data['event_name']} for user {interaction.user.id} with {len(added_teammates)} teammates"
        )

    # --- Slash Command: Add Custom Event ---
    @app_commands.command(
        name="add_custom",
        description="Add a custom CTF event (not on CTFtime).",
    )
    @app_commands.describe(
        name="Name of the CTF event",
        start_date="Start date (YYYY-MM-DD)",
        start_time="Start time in 24h format (HH:MM)",
        end_date="End date (YYYY-MM-DD)",
        end_time="End time in 24h format (HH:MM)",
        url="Official event URL (optional)",
        format="Event format: Jeopardy, Attack-Defense, etc. (optional)",
        description="Short description of the event (optional)",
        teammates="Tag teammates to add to this event (optional)"
    )
    async def add_custom_event(
        self,
        interaction: discord.Interaction,
        name: str,
        start_date: str,
        start_time: str,
        end_date: str,
        end_time: str,
        url: Optional[str] = None,
        format: Optional[str] = None,
        description: Optional[str] = None,
        teammates: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        # Parse dates
        try:
            start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.followup.send(
                "Invalid date/time format. Use YYYY-MM-DD for dates and HH:MM for times.",
                ephemeral=True,
            )
            return

        # Get user timezone and convert to UTC
        user_settings = await database.get_user_settings(interaction.user.id)
        user_tz = pytz.timezone(user_settings.get("timezone", "Europe/Paris"))

        start_dt = user_tz.localize(start_dt).astimezone(pytz.utc)
        end_dt = user_tz.localize(end_dt).astimezone(pytz.utc)

        # Validate times
        if end_dt <= start_dt:
            await interaction.followup.send(
                "End time must be after start time.", ephemeral=True
            )
            return

        if end_dt < datetime.now(pytz.utc):
            await interaction.followup.send(
                "Cannot add an event that has already ended.", ephemeral=True
            )
            return

        # Generate event name
        event_name = name.strip().replace(" ", "-").replace('"', "").replace("'", "")

        event_data = {
            "event_name": event_name,
            "title": name,
            "start": start_dt,
            "finish": end_dt,
            "url": url or "",
            "format": format or "Custom",
            "description": description or "",
            "organizers": "Custom Event",
            "weight": 0.0,
            "participants": 0,
            "is_custom": 1,
            "created_by": interaction.user.id,
        }

        server_id = interaction.guild.id if interaction.guild else None
        success = await database.add_event_to_user(
            interaction.user.id, event_data, server_id
        )

        if not success:
            await interaction.followup.send(
                f"An event with the name **{event_name}** already exists.",
                ephemeral=True,
            )
            return

        # Get event ID and add teammates
        event = await database.get_event_by_name(event_name)
        added_teammates = []

        if teammates and event:
            mention_pattern = r"<@!?(\d+)>"
            mentioned_ids = re.findall(mention_pattern, teammates)

            for user_id_str in mentioned_ids:
                member_id = int(user_id_str)
                if member_id != interaction.user.id:
                    added = await database.add_event_member(
                        event["id"], interaction.user.id, member_id
                    )
                    if added:
                        added_teammates.append(member_id)

        embed = discord.Embed(
            title="✅ Custom Event Created",
            description=f"Successfully created **{name}**",
            color=CYBER_THEME_COLOR,
        )
        embed.add_field(
            name="Start Time",
            value=helpers.format_discord_timestamp(start_dt),
            inline=True,
        )
        embed.add_field(
            name="End Time",
            value=helpers.format_discord_timestamp(end_dt),
            inline=True,
        )
        if format:
            embed.add_field(name="Format", value=format, inline=True)
        if added_teammates:
            teammates_mentions = ", ".join([f"<@{uid}>" for uid in added_teammates])
            embed.add_field(name="👥 Teammates", value=teammates_mentions, inline=False)

        # Create private thread for team if teammates were added
        thread = None
        if added_teammates and interaction.guild:
            thread = await self.create_team_thread(
                interaction, event_name, event_data,
                interaction.user.id, added_teammates
            )
            if thread:
                embed.add_field(
                    name="💬 Team Thread",
                    value=f"Created: {thread.mention}",
                    inline=False,
                )

        embed.set_footer(text="Custom event • Use /agenda to view your events")
        await interaction.followup.send(embed=embed, ephemeral=True)

        self.logger.info(f"User {interaction.user.id} created custom event: {event_name}")

    # --- Slash Command: View Agenda ---
    @app_commands.command(
        name="agenda", description="Displays your personal CTF event agenda."
    )
    @app_commands.describe(
        show_past="Include past events in the list"
    )
    async def view_agenda(
        self,
        interaction: discord.Interaction,
        show_past: bool = False
    ):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(f"User {interaction.user.id} requested their agenda.")

        user_events = await database.get_user_events(interaction.user.id, include_past=show_past)

        if not user_events:
            await interaction.followup.send(
                "Your agenda is empty. Use `/add` or `/add_custom` to add events!",
                ephemeral=True
            )
            return

        # Get user settings
        user_settings = await database.get_user_settings(interaction.user.id)

        embed = discord.Embed(
            title=f"📅 {interaction.user.display_name}'s CTF Agenda",
            description=f"{'All' if show_past else 'Upcoming'} CTF events ({len(user_events)} total):",
            color=CYBER_THEME_COLOR,
        )

        now = datetime.now(pytz.utc)

        for event in user_events[:25]:  # Discord embed field limit
            start_dt = event["start_time"]
            end_dt = event["end_time"]
            if isinstance(start_dt, str):
                start_dt = datetime.fromisoformat(start_dt)
            if isinstance(end_dt, str):
                end_dt = datetime.fromisoformat(end_dt)

            # Make timezone aware if needed
            if start_dt.tzinfo is None:
                start_dt = pytz.utc.localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = pytz.utc.localize(end_dt)

            # Determine status
            if end_dt < now:
                status = "🏁 Finished"
            elif start_dt <= now <= end_dt:
                status = "🔴 LIVE NOW"
            else:
                status = "⏳ Upcoming"

            # Check if custom event
            is_custom = event.get("is_custom", 0)
            icon = "🎯" if is_custom else "🛡️"

            embed.add_field(
                name=f"{icon} {event['event_name']} [{status}]",
                value=(
                    f"**Start:** {helpers.format_discord_timestamp(start_dt)}\n"
                    f"**End:** {helpers.format_discord_timestamp(end_dt)}"
                ),
                inline=False,
            )

        if len(user_events) > 25:
            embed.set_footer(text=f"Showing 25 of {len(user_events)} events • Use /search to filter")
        else:
            embed.set_footer(text="Use /details <event_name> for more info • /calendar to export")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: Event Details ---
    @app_commands.command(
        name="details",
        description="Shows detailed information about an event in your agenda.",
    )
    @app_commands.describe(
        event_name="The name of the event from your /agenda."
    )
    async def event_details(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(f"User {interaction.user.id} requested details for event: {event_name}")

        event = await database.get_event_details(interaction.user.id, event_name)

        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda. Check the name using `/agenda`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"ℹ️ {event.get('title', event['event_name'])}",
            description=event.get("description", "No description available.")[:1000],
            color=CYBER_THEME_COLOR,
        )

        # Parse times
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
            name="End Time",
            value=helpers.format_discord_timestamp(end_dt),
            inline=True,
        )
        embed.add_field(name="Format", value=event.get("format") or "N/A", inline=True)
        embed.add_field(name="Organizers", value=event.get("organizers") or "N/A", inline=True)

        weight = event.get("weight", 0)
        if weight:
            embed.add_field(name="Weight", value=f"{weight:.2f}", inline=True)

        participants = event.get("participants", 0)
        if participants:
            embed.add_field(name="Participants", value=str(participants), inline=True)

        # Links
        links = []
        if event.get("ctftime_url"):
            links.append(f"[CTFtime]({event['ctftime_url']})")
        if event.get("event_url"):
            links.append(f"[Official Site]({event['event_url']})")
        if links:
            embed.add_field(name="Links", value=" | ".join(links), inline=False)

        # Get team members
        if event.get("id"):
            members = await database.get_event_members(event["id"], interaction.user.id)
            if members:
                member_mentions = ", ".join([f"<@{mid}>" for mid in members])
                embed.add_field(name="👥 Your Team", value=member_mentions, inline=False)

        # Get writeups
        if event.get("id"):
            writeups = await database.get_event_writeups(event["id"])
            if writeups:
                writeup_list = "\n".join([
                    f"• [{w.get('title') or w.get('challenge_name') or 'Writeup'}]({w['url']})"
                    for w in writeups[:5]
                ])
                embed.add_field(name="📝 Writeups", value=writeup_list, inline=False)

        is_custom = event.get("is_custom", 0)
        embed.set_footer(text="Custom Event" if is_custom else "CTFtime Event")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Autocomplete for Event Name ---
    async def event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
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

    @event_details.autocomplete("event_name")
    async def details_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.event_autocomplete(interaction, current)

    # --- Slash Command: Add Teammate ---
    @app_commands.command(
        name="team_add",
        description="Add a teammate to one of your events.",
    )
    @app_commands.describe(
        event_name="The event to add the teammate to",
        member="The teammate to add"
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def add_teammate(
        self,
        interaction: discord.Interaction,
        event_name: str,
        member: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)

        event = await database.get_event_details(interaction.user.id, event_name)
        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda.",
                ephemeral=True
            )
            return

        if member.id == interaction.user.id:
            await interaction.followup.send(
                "You can't add yourself as a teammate!",
                ephemeral=True
            )
            return

        success = await database.add_event_member(event["id"], interaction.user.id, member.id)

        if success:
            response_text = f"✅ Added {member.mention} to **{event_name}**"

            # Check if this is the first teammate - if so, create a thread
            all_members = await database.get_event_members(event["id"], interaction.user.id)
            if len(all_members) == 1 and interaction.guild:
                # First teammate added - create a team thread
                thread = await self.create_team_thread(
                    interaction, event_name, event,
                    interaction.user.id, [member.id]
                )
                if thread:
                    response_text += f"\n💬 Team thread created: {thread.mention}"
            elif interaction.guild:
                # Thread may already exist - try to add the new member to it
                # Search for existing thread in the notification channel
                server_settings = await database.get_server_settings(interaction.guild.id)
                channel_id = server_settings.get("notification_channel_id")
                channel = None
                if channel_id:
                    try:
                        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden):
                        pass
                if not channel and interaction.channel:
                    channel = interaction.channel

                if channel and hasattr(channel, 'threads'):
                    thread_name = f"CTF - {event_name}"
                    for thread in channel.threads:
                        if thread.name == thread_name:
                            try:
                                await thread.add_user(member)
                                response_text += f"\n💬 Added to team thread: {thread.mention}"
                            except (discord.Forbidden, discord.NotFound):
                                pass
                            break

            await interaction.followup.send(response_text, ephemeral=True)

            # Notify the teammate via DM
            try:
                start_dt = event["start_time"]
                if isinstance(start_dt, str):
                    start_dt = datetime.fromisoformat(start_dt)

                dm_embed = discord.Embed(
                    title="📅 You've been added to a CTF!",
                    description=f"**{interaction.user.display_name}** added you to **{event_name}**",
                    color=CYBER_THEME_COLOR,
                )
                dm_embed.add_field(
                    name="Start Time",
                    value=helpers.format_discord_timestamp(start_dt),
                    inline=True,
                )
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                pass
        else:
            await interaction.followup.send(
                f"{member.mention} is already in your team for this event.",
                ephemeral=True
            )

    # --- Slash Command: Remove Teammate ---
    @app_commands.command(
        name="team_remove",
        description="Remove a teammate from one of your events.",
    )
    @app_commands.describe(
        event_name="The event to remove the teammate from",
        member="The teammate to remove"
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def remove_teammate(
        self,
        interaction: discord.Interaction,
        event_name: str,
        member: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)

        event = await database.get_event_details(interaction.user.id, event_name)
        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda.",
                ephemeral=True
            )
            return

        success = await database.remove_event_member(event["id"], interaction.user.id, member.id)

        if success:
            await interaction.followup.send(
                f"✅ Removed {member.mention} from **{event_name}**",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"{member.mention} is not in your team for this event.",
                ephemeral=True
            )

    # --- Slash Command: View Team ---
    @app_commands.command(
        name="team",
        description="View the team for one of your events.",
    )
    @app_commands.describe(event_name="The event to view the team for")
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def view_team(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer(ephemeral=True)

        event = await database.get_event_details(interaction.user.id, event_name)
        if not event:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda.",
                ephemeral=True
            )
            return

        members = await database.get_event_members(event["id"], interaction.user.id)

        embed = discord.Embed(
            title=f"👥 Team for {event_name}",
            color=CYBER_THEME_COLOR,
        )

        if members:
            member_list = [f"• <@{mid}>" for mid in members]
            embed.description = f"**Team Leader:** {interaction.user.mention}\n\n**Members:**\n" + "\n".join(member_list)
        else:
            embed.description = f"**Team Leader:** {interaction.user.mention}\n\n*No teammates added yet. Use `/team_add` to add members.*"

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: Remove Event ---
    @app_commands.command(
        name="remove", description="Removes an event from your personal agenda."
    )
    @app_commands.describe(
        event_name="The name of the event to remove."
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def remove_event(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer(ephemeral=True)
        self.logger.info(f"User {interaction.user.id} attempting to remove event: {event_name}")

        success = await database.remove_event_from_user(interaction.user.id, event_name)

        if success:
            await interaction.followup.send(
                f"🗑️ Event `{event_name}` removed from your agenda.",
                ephemeral=True
            )
            self.logger.info(f"Successfully removed event {event_name} for user {interaction.user.id}")
        else:
            await interaction.followup.send(
                f"Event `{event_name}` not found in your agenda.",
                ephemeral=True,
            )

    # --- Slash Command: Clear Agenda ---
    @app_commands.command(
        name="clear", description="Removes ALL events from your personal agenda."
    )
    async def clear_agenda(self, interaction: discord.Interaction):
        view = ClearConfirmationView(interaction.user)
        embed = discord.Embed(
            title="⚠️ Confirm Clear Agenda",
            description="Are you sure you want to remove **ALL** events from your personal agenda?\n\n*Note: Events with writeups will be preserved in history.*",
            color=0xFFCC00,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        self.logger.info(f"User {interaction.user.id} initiated clear agenda confirmation.")

    # --- Slash Command: Search Events ---
    @app_commands.command(
        name="search",
        description="Search for events in your agenda."
    )
    @app_commands.describe(query="Search term (name, description, organizer)")
    async def search_events(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)

        results = await database.search_user_events(interaction.user.id, query)

        if not results:
            await interaction.followup.send(
                f"No events found matching `{query}`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🔍 Search Results for '{query}'",
            description=f"Found {len(results)} event(s):",
            color=CYBER_THEME_COLOR,
        )

        for event in results[:10]:
            start_dt = event["start_time"]
            if isinstance(start_dt, str):
                start_dt = datetime.fromisoformat(start_dt)

            embed.add_field(
                name=f"🛡️ {event['event_name']}",
                value=f"**Start:** {helpers.format_discord_timestamp(start_dt)}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Slash Command: Export Calendar ---
    @app_commands.command(
        name="calendar",
        description="Export your agenda as an iCal file (.ics) for your calendar app."
    )
    @app_commands.describe(
        event_name="Export a specific event (leave empty for all upcoming events)"
    )
    async def export_calendar(
        self,
        interaction: discord.Interaction,
        event_name: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        if event_name:
            event = await database.get_event_details(interaction.user.id, event_name)
            if not event:
                await interaction.followup.send(
                    f"Event `{event_name}` not found in your agenda.",
                    ephemeral=True
                )
                return
            events = [event]
            filename = f"{event_name}.ics"
        else:
            events = await database.get_user_events(interaction.user.id)
            if not events:
                await interaction.followup.send(
                    "Your agenda is empty!",
                    ephemeral=True
                )
                return
            filename = "ctf_agenda.ics"

        # Generate iCal content
        ical_content = helpers.generate_ical(events)

        # Create file
        file = discord.File(
            fp=__import__('io').BytesIO(ical_content.encode('utf-8')),
            filename=filename
        )

        embed = discord.Embed(
            title="📅 Calendar Export",
            description=(
                f"Here's your calendar file with **{len(events)}** event(s).\n\n"
                "**How to use:**\n"
                "• **Google Calendar:** Import via Settings → Import & Export\n"
                "• **Outlook:** Double-click the file or import via File → Open & Export\n"
                "• **Apple Calendar:** Double-click the file to add events\n\n"
                "*Reminders are set for 1 hour before and at event start.*"
            ),
            color=CYBER_THEME_COLOR,
        )

        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @export_calendar.autocomplete("event_name")
    async def calendar_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.event_autocomplete(interaction, current)


# --- Confirmation View for Clear ---
class ClearConfirmationView(discord.ui.View):
    def __init__(self, author: discord.User, timeout=60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.logger = logging.getLogger(f"{__name__}.ClearConfirmationView")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This confirmation is not for you.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
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
        self.logger.info(f"User {interaction.user.id} cleared {deleted_count} events.")
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


# --- Setup Function ---
async def setup(bot: commands.Bot):
    await bot.add_cog(EventCommands(bot))
