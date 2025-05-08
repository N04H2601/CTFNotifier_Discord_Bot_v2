# cogs/notification_service.py

import discord
from discord.ext import commands, tasks
import logging
from datetime import datetime, timedelta
import pytz
import asyncio

from utils import database, helpers

# --- Constants & Configuration ---
CYBER_THEME_COLOR = 0x006400  # Cyan/Aqua - consistent with other cogs
NOTIFICATION_CHECK_INTERVAL_SECONDS = 20  # Check every 30 seconds
PAST_EVENT_CLEANUP_INTERVAL_HOURS = 1  # Clean up old events every hour


class NotificationService(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.check_events_loop.start()
        self.cleanup_past_events_loop.start()
        self.logger.info("NotificationService Cog initialized and loops started.")

    def cog_unload(self):
        self.check_events_loop.cancel()
        self.cleanup_past_events_loop.cancel()
        self.logger.info("NotificationService loops cancelled.")

    @tasks.loop(seconds=NOTIFICATION_CHECK_INTERVAL_SECONDS)
    async def check_events_loop(self):
        # Wait until the bot is ready
        await self.bot.wait_until_ready()
        self.logger.debug("Running notification check...")

        try:
            all_events = await database.get_all_events_for_notifications()
            now_utc = datetime.now(pytz.utc)

            for event in all_events:
                user_id = event["user_id"]
                event_name = event["event_name"]

                # Ensure times are timezone-aware UTC datetimes
                start_time = event["start_time"]
                end_time = event["end_time"]
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time)
                if isinstance(end_time, str):
                    end_time = datetime.fromisoformat(end_time)

                if start_time.tzinfo is None:
                    start_time = pytz.utc.localize(start_time)
                else:
                    start_time = start_time.astimezone(pytz.utc)

                if end_time.tzinfo is None:
                    end_time = pytz.utc.localize(end_time)
                else:
                    end_time = end_time.astimezone(pytz.utc)

                user = self.bot.get_user(user_id)
                if not user:
                    try:
                        self.logger.debug(
                            f"User {user_id} not in cache, attempting to fetch."
                        )
                        user = await self.bot.fetch_user(user_id)
                        self.logger.debug(f"Successfully fetched user {user_id}.")
                    except discord.NotFound:
                        self.logger.warning(
                            f"Could not find user {user_id} via API (NotFound). Skipping notification."
                        )
                        continue
                    except discord.HTTPException as e:
                        self.logger.error(
                            f"HTTP error fetching user {user_id}: {e}. Skipping notification."
                        )
                        continue
                    except Exception as e:
                        self.logger.error(
                            f"Unexpected error fetching user {user_id}: {e}. Skipping notification.",
                            exc_info=True,
                        )
                        continue

                # If user is still None after fetch attempt (shouldn't happen with proper exceptions, but belt-and-suspenders)
                if not user:
                    self.logger.error(
                        f"User object for {user_id} is None even after fetch attempt. Skipping notification."
                    )
                    continue

                # --- Check Notification Conditions ---

                # 1 Hour Reminder (Before Start)
                reminder_flag = bool(event.get("reminder_sent", 0))
                reminder_time = start_time - timedelta(hours=1)
                # Trigger within the first 5 minutes after the 1-hour-before mark
                if (
                    not reminder_flag
                    and reminder_time <= now_utc < reminder_time + timedelta(minutes=5)
                ):
                    embed = discord.Embed(
                        title=f"🚨 CTF Reminder: {event_name}",
                        description=f"This event starts in about 1 hour: {helpers.format_discord_timestamp(start_time, style='R')} ({helpers.format_discord_timestamp(start_time, style='F')})!",
                        color=0xFFCC00,  # Warning Yellow
                    )
                    embed.add_field(
                        name="Event Link",
                        value=event.get("ctftime_url", "N/A"),
                        inline=False,
                    )
                    try:
                        await user.send(embed=embed)
                        await database.update_notification_flag(
                            user_id, event_name, "reminder_sent", True
                        )
                        self.logger.info(
                            f"Sent 1-hour reminder for 	{event_name}	 to user {user_id}"
                        )
                    except discord.Forbidden:
                        self.logger.warning(
                            f"Could not send DM reminder to user {user_id} (DMs likely disabled)."
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error sending reminder DM to {user_id} for {event_name}: {e}",
                            exc_info=True,
                        )

                # Good Luck Message (At Start)
                good_luck_flag = bool(event.get("good_luck_sent", 0))
                if (
                    not good_luck_flag
                    and start_time <= now_utc < start_time + timedelta(minutes=1)
                ):
                    embed = discord.Embed(
                        title=f"🍀 Good Luck For: {event_name}",
                        description=f"This event has just started and runs until: {helpers.format_discord_timestamp(end_time, style='F')} ({helpers.format_discord_timestamp(end_time, style='R')}).",
                        color=0x00FF00,  # Green
                    )
                    embed.add_field(
                        name="Event Link",
                        value=event.get("ctftime_url", "N/A"),
                        inline=False,
                    )
                    try:
                        await user.send(embed=embed)
                        await database.update_notification_flag(
                            user_id, event_name, "good_luck_sent", True
                        )
                        self.logger.info(
                            f"Sent good luck message for 	{event_name}	 to user {user_id}"
                        )
                    except discord.Forbidden:
                        self.logger.warning(
                            f"Could not send DM good luck message to user {user_id}."
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error sending good luck DM to {user_id} for {event_name}: {e}",
                            exc_info=True,
                        )

                # Ending Soon Message (1 Hour Before End)
                ending_soon_flag = bool(event.get("ending_soon_sent", 0))
                ending_soon_time = end_time - timedelta(hours=1)
                # Trigger within the first 5 minutes after the 1-hour-before-end mark
                if (
                    not ending_soon_flag
                    and ending_soon_time
                    <= now_utc
                    < ending_soon_time + timedelta(minutes=5)
                ):
                    embed = discord.Embed(
                        title=f"⏰ Ending Soon: {event_name}",
                        description=f"This event ends in about 1 hour: {helpers.format_discord_timestamp(end_time, style='R')} ({helpers.format_discord_timestamp(end_time, style='F')})! Submit your flags!",
                        color=0xFFA500,  # Orange
                    )
                    embed.add_field(
                        name="Event Link",
                        value=event.get("ctftime_url", "N/A"),
                        inline=False,
                    )
                    try:
                        await user.send(embed=embed)
                        await database.update_notification_flag(
                            user_id, event_name, "ending_soon_sent", True
                        )
                        self.logger.info(
                            f"Sent ending soon message for 	{event_name}	 to user {user_id}"
                        )
                    except discord.Forbidden:
                        self.logger.warning(
                            f"Could not send DM ending soon message to user {user_id}."
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error sending ending soon DM to {user_id} for {event_name}: {e}",
                            exc_info=True,
                        )

                # Congratulations Message (At End)
                congrats_flag = bool(event.get("congratulations_sent", 0))
                # Trigger exactly at or slightly after the end time, but only once
                if not congrats_flag and now_utc >= end_time:
                    embed = discord.Embed(
                        title=f"🎉 Congratulations For: {event_name}",
                        description=f"This event ended: {helpers.format_discord_timestamp(end_time, style='F')}. Well done!",
                        color=CYBER_THEME_COLOR,  # Cyan/Aqua
                    )
                    # No event link needed here usually
                    try:
                        await user.send(embed=embed)
                        await database.update_notification_flag(
                            user_id, event_name, "congratulations_sent", True
                        )
                        self.logger.info(
                            f"Sent congratulations message for 	{event_name}	 to user {user_id}"
                        )
                    except discord.Forbidden:
                        self.logger.warning(
                            f"Could not send DM congratulations message to user {user_id}."
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error sending congratulations DM to {user_id} for {event_name}: {e}",
                            exc_info=True,
                        )

                # Note: The original bot sent a 'congratulations' message *after* the event ended.
                # This is less useful as a notification and also triggered deletion.
                # We now handle deletion separately in the cleanup task.

        except Exception as e:
            self.logger.error(f"Error in notification loop: {e}", exc_info=True)
            # Avoid spamming logs on repeated errors, wait a bit longer
            await asyncio.sleep(NOTIFICATION_CHECK_INTERVAL_SECONDS * 5)

    @tasks.loop(hours=PAST_EVENT_CLEANUP_INTERVAL_HOURS)
    async def cleanup_past_events_loop(self):
        await self.bot.wait_until_ready()
        self.logger.info("Running past event cleanup...")
        try:
            deleted_count = await database.remove_past_events()
            if deleted_count > 0:
                self.logger.info(
                    f"Cleaned up {deleted_count} past events from the database."
                )
            else:
                self.logger.info("No past events found to clean up.")
        except Exception as e:
            self.logger.error(f"Error during past event cleanup: {e}", exc_info=True)

    @check_events_loop.before_loop
    @cleanup_past_events_loop.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()
        self.logger.info("Notification loops are ready to start.")


# --- Setup Function --- #
async def setup(bot: commands.Bot):
    await bot.add_cog(NotificationService(bot))
