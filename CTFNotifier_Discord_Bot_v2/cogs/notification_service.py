# cogs/notification_service.py

import discord
from discord.ext import commands, tasks
import logging
from datetime import datetime, timedelta
import pytz
import asyncio

from utils import database, helpers

# --- Constants & Configuration ---
CYBER_THEME_COLOR = 0x00FFFF  # Cyan/Aqua - consistent with other cogs
NOTIFICATION_CHECK_INTERVAL_SECONDS = 30  # Check every 30 seconds
CLEANUP_INTERVAL_HOURS = 24  # Clean up old events every 24 hours


class NotificationService(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.check_events_loop.start()
        self.cleanup_old_events_loop.start()
        self.logger.info("NotificationService Cog initialized and loops started.")

    def cog_unload(self):
        self.check_events_loop.cancel()
        self.cleanup_old_events_loop.cancel()
        self.logger.info("NotificationService loops cancelled.")

    async def send_dm_notification(
        self,
        user_id: int,
        embed: discord.Embed,
        event_name: str,
        notification_type: str
    ) -> bool:
        """Send a DM notification to a user. Returns True if successful."""
        try:
            user = self.bot.get_user(user_id)
            if not user:
                user = await self.bot.fetch_user(user_id)

            await user.send(embed=embed)
            self.logger.info(f"Sent {notification_type} DM for '{event_name}' to user {user_id}")
            return True

        except discord.Forbidden:
            self.logger.warning(f"Cannot send DM to user {user_id} (DMs disabled)")
            return False
        except discord.NotFound:
            self.logger.warning(f"User {user_id} not found")
            return False
        except Exception as e:
            self.logger.error(f"Error sending DM to {user_id}: {e}", exc_info=True)
            return False

    async def send_channel_notification(
        self,
        server_id: int,
        embed: discord.Embed,
        event_name: str,
        user_mentions: list = None
    ) -> bool:
        """Send a channel notification. Returns True if successful."""
        try:
            server_settings = await database.get_server_settings(server_id)
            channel_id = server_settings.get("notification_channel_id")

            if not channel_id:
                return False

            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)

            # Build mention string
            mention_str = ""
            if user_mentions:
                mention_str = " ".join([f"<@{uid}>" for uid in user_mentions])

            await channel.send(content=mention_str if mention_str else None, embed=embed)
            self.logger.info(f"Sent channel notification for '{event_name}' to channel {channel_id}")
            return True

        except discord.Forbidden:
            self.logger.warning(f"Cannot send to channel in server {server_id} (no permission)")
            return False
        except discord.NotFound:
            self.logger.warning(f"Channel not found for server {server_id}")
            return False
        except Exception as e:
            self.logger.error(f"Error sending channel notification: {e}", exc_info=True)
            return False

    @tasks.loop(seconds=NOTIFICATION_CHECK_INTERVAL_SECONDS)
    async def check_events_loop(self):
        """Main loop that checks for events and sends notifications."""
        await self.bot.wait_until_ready()

        try:
            all_events = await database.get_all_events_for_notifications()
            now_utc = datetime.now(pytz.utc)

            # Group events by event_id for channel notifications
            processed_channel_notifications = set()

            for event in all_events:
                user_id = event["user_id"]
                event_name = event["event_name"]
                event_id = event["id"]
                server_id = event.get("server_id")

                # Parse times
                start_time = event["start_time"]
                end_time = event["end_time"]
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time)
                if isinstance(end_time, str):
                    end_time = datetime.fromisoformat(end_time)

                # Ensure timezone awareness
                if start_time.tzinfo is None:
                    start_time = pytz.utc.localize(start_time)
                else:
                    start_time = start_time.astimezone(pytz.utc)

                if end_time.tzinfo is None:
                    end_time = pytz.utc.localize(end_time)
                else:
                    end_time = end_time.astimezone(pytz.utc)

                # Get user notification preferences (with defaults)
                pref_reminder = event.get("reminder_1h_before", 1)
                pref_good_luck = event.get("good_luck_on_start", 1)
                pref_ending_soon = event.get("ending_soon_1h", 1)
                pref_congrats = event.get("congratulations_on_end", 1)
                pref_channel = event.get("channel_notification", 1)

                # Get event members for team notifications
                event_members = await database.get_event_members(event_id, user_id)
                all_participants = [user_id] + event_members

                ctftime_url = event.get("ctftime_url", "N/A")

                # =========================================
                # 1. Channel Notification (1h before start)
                # =========================================
                channel_key = f"{event_id}_{server_id}_channel"
                channel_reminder_sent = bool(event.get("channel_reminder_sent", 0))
                reminder_time = start_time - timedelta(hours=1)

                if (
                    server_id
                    and pref_channel
                    and not channel_reminder_sent
                    and channel_key not in processed_channel_notifications
                    and reminder_time <= now_utc < reminder_time + timedelta(minutes=5)
                ):
                    embed = discord.Embed(
                        title=f"🚨 CTF Starting Soon: {event_name}",
                        description=(
                            f"This event starts in about **1 hour**!\n\n"
                            f"**Start:** {helpers.format_discord_timestamp(start_time, style='R')} "
                            f"({helpers.format_discord_timestamp(start_time, style='F')})"
                        ),
                        color=0xFFCC00,  # Warning Yellow
                    )
                    if ctftime_url != "N/A":
                        embed.add_field(name="Event Link", value=ctftime_url, inline=False)

                    success = await self.send_channel_notification(
                        server_id, embed, event_name, all_participants
                    )
                    if success:
                        # Mark as sent for all users with this event
                        await database.update_notification_flag(
                            user_id, event_name, "channel_reminder_sent", True
                        )
                        processed_channel_notifications.add(channel_key)

                # =========================================
                # 2. DM: 1 Hour Reminder (Before Start)
                # =========================================
                reminder_flag = bool(event.get("reminder_sent", 0))
                if (
                    pref_reminder
                    and not reminder_flag
                    and reminder_time <= now_utc < reminder_time + timedelta(minutes=5)
                ):
                    embed = discord.Embed(
                        title=f"🚨 CTF Reminder: {event_name}",
                        description=(
                            f"This event starts in about 1 hour!\n\n"
                            f"**Start:** {helpers.format_discord_timestamp(start_time, style='R')} "
                            f"({helpers.format_discord_timestamp(start_time, style='F')})"
                        ),
                        color=0xFFCC00,
                    )
                    if ctftime_url != "N/A":
                        embed.add_field(name="Event Link", value=ctftime_url, inline=False)

                    # Send to event owner
                    await self.send_dm_notification(user_id, embed, event_name, "reminder")
                    await database.update_notification_flag(user_id, event_name, "reminder_sent", True)

                    # Send to team members
                    for member_id in event_members:
                        member_embed = discord.Embed(
                            title=f"🚨 CTF Reminder: {event_name}",
                            description=(
                                f"A CTF you're participating in starts in about 1 hour!\n\n"
                                f"**Start:** {helpers.format_discord_timestamp(start_time, style='R')}"
                            ),
                            color=0xFFCC00,
                        )
                        if ctftime_url != "N/A":
                            member_embed.add_field(name="Event Link", value=ctftime_url, inline=False)
                        await self.send_dm_notification(member_id, member_embed, event_name, "team_reminder")

                # =========================================
                # 3. DM: Good Luck Message (At Start)
                # =========================================
                good_luck_flag = bool(event.get("good_luck_sent", 0))
                if (
                    pref_good_luck
                    and not good_luck_flag
                    and start_time <= now_utc < start_time + timedelta(minutes=2)
                ):
                    embed = discord.Embed(
                        title=f"🍀 Good Luck: {event_name}",
                        description=(
                            f"The CTF has just started! Good luck!\n\n"
                            f"**Ends:** {helpers.format_discord_timestamp(end_time, style='F')} "
                            f"({helpers.format_discord_timestamp(end_time, style='R')})"
                        ),
                        color=0x00FF00,  # Green
                    )
                    if ctftime_url != "N/A":
                        embed.add_field(name="Event Link", value=ctftime_url, inline=False)

                    await self.send_dm_notification(user_id, embed, event_name, "good_luck")
                    await database.update_notification_flag(user_id, event_name, "good_luck_sent", True)

                    # Send to team members
                    for member_id in event_members:
                        await self.send_dm_notification(member_id, embed, event_name, "team_good_luck")

                # =========================================
                # 4. DM: Ending Soon Message (1h Before End)
                # =========================================
                ending_soon_flag = bool(event.get("ending_soon_sent", 0))
                ending_soon_time = end_time - timedelta(hours=1)
                if (
                    pref_ending_soon
                    and not ending_soon_flag
                    and ending_soon_time <= now_utc < ending_soon_time + timedelta(minutes=5)
                ):
                    embed = discord.Embed(
                        title=f"⏰ Ending Soon: {event_name}",
                        description=(
                            f"This CTF ends in about 1 hour! Submit your flags!\n\n"
                            f"**Ends:** {helpers.format_discord_timestamp(end_time, style='R')} "
                            f"({helpers.format_discord_timestamp(end_time, style='F')})"
                        ),
                        color=0xFFA500,  # Orange
                    )
                    if ctftime_url != "N/A":
                        embed.add_field(name="Event Link", value=ctftime_url, inline=False)

                    await self.send_dm_notification(user_id, embed, event_name, "ending_soon")
                    await database.update_notification_flag(user_id, event_name, "ending_soon_sent", True)

                    # Send to team members
                    for member_id in event_members:
                        await self.send_dm_notification(member_id, embed, event_name, "team_ending_soon")

                # =========================================
                # 5. DM: Congratulations Message (At End)
                # =========================================
                congrats_flag = bool(event.get("congratulations_sent", 0))
                if (
                    pref_congrats
                    and not congrats_flag
                    and now_utc >= end_time
                    and now_utc < end_time + timedelta(minutes=10)
                ):
                    embed = discord.Embed(
                        title=f"🎉 CTF Finished: {event_name}",
                        description=(
                            f"This CTF has ended. Great job!\n\n"
                            f"Don't forget to add your writeups with `/writeup add`!"
                        ),
                        color=CYBER_THEME_COLOR,
                    )

                    await self.send_dm_notification(user_id, embed, event_name, "congratulations")
                    await database.update_notification_flag(user_id, event_name, "congratulations_sent", True)

                    # Send to team members
                    for member_id in event_members:
                        await self.send_dm_notification(member_id, embed, event_name, "team_congratulations")

        except Exception as e:
            self.logger.error(f"Error in notification loop: {e}", exc_info=True)
            await asyncio.sleep(NOTIFICATION_CHECK_INTERVAL_SECONDS * 2)

    @tasks.loop(hours=CLEANUP_INTERVAL_HOURS)
    async def cleanup_old_events_loop(self):
        """Clean up old events without writeups."""
        await self.bot.wait_until_ready()
        self.logger.info("Running old event cleanup...")
        try:
            deleted_count = await database.cleanup_old_events(days_old=365)
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old events from the database.")
            else:
                self.logger.debug("No old events to clean up.")
        except Exception as e:
            self.logger.error(f"Error during old event cleanup: {e}", exc_info=True)

    @check_events_loop.before_loop
    async def before_check_events(self):
        await self.bot.wait_until_ready()
        self.logger.info("Notification check loop is ready.")

    @cleanup_old_events_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
        self.logger.info("Cleanup loop is ready.")


# --- Setup Function ---
async def setup(bot: commands.Bot):
    await bot.add_cog(NotificationService(bot))
