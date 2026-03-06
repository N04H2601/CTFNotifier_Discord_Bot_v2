# cogs/settings_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from utils import database, helpers

# --- Constants ---
CYBER_THEME_COLOR = 0x00FFFF


class SettingsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}")
        self.logger.info("SettingsCommands Cog initialized.")

    # --- Timezone Commands ---
    @app_commands.command(
        name="timezone",
        description="Set your timezone for event times display."
    )
    @app_commands.describe(
        timezone="Your timezone (e.g., Europe/Paris, America/New_York)"
    )
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        await interaction.response.defer(ephemeral=True)

        if not helpers.is_valid_timezone(timezone):
            # Suggest similar timezones
            suggestions = helpers.get_timezone_choices(timezone)[:5]
            suggestion_text = "\n".join([f"• `{tz}`" for tz in suggestions]) if suggestions else "Try using the autocomplete!"

            await interaction.followup.send(
                f"Invalid timezone: `{timezone}`\n\n**Did you mean:**\n{suggestion_text}",
                ephemeral=True
            )
            return

        await database.update_user_timezone(interaction.user.id, timezone)

        embed = discord.Embed(
            title="⏰ Timezone Updated",
            description=f"Your timezone has been set to **{timezone}**",
            color=CYBER_THEME_COLOR,
        )
        embed.add_field(
            name="Current Time",
            value=helpers.format_datetime_local(
                __import__('datetime').datetime.now(__import__('pytz').utc),
                timezone
            ),
            inline=False
        )
        embed.set_footer(text="Event times in custom events will use this timezone")

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"User {interaction.user.id} set timezone to {timezone}")

    @set_timezone.autocomplete("timezone")
    async def timezone_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = helpers.get_timezone_choices(current)
        return [app_commands.Choice(name=tz, value=tz) for tz in choices]

    # --- Notification Settings ---
    @app_commands.command(
        name="notifications",
        description="Configure your notification preferences."
    )
    @app_commands.describe(
        reminder_1h="Receive DM 1 hour before CTF starts",
        good_luck="Receive DM when CTF starts",
        ending_soon="Receive DM 1 hour before CTF ends",
        congratulations="Receive DM when CTF ends",
        channel_notifications="Receive channel notifications (if configured)"
    )
    async def set_notifications(
        self,
        interaction: discord.Interaction,
        reminder_1h: Optional[bool] = None,
        good_luck: Optional[bool] = None,
        ending_soon: Optional[bool] = None,
        congratulations: Optional[bool] = None,
        channel_notifications: Optional[bool] = None
    ):
        await interaction.response.defer(ephemeral=True)

        # If no options provided, show current settings
        if all(opt is None for opt in [reminder_1h, good_luck, ending_soon, congratulations, channel_notifications]):
            settings = await database.get_user_settings(interaction.user.id)

            embed = discord.Embed(
                title="🔔 Your Notification Settings",
                description="Here are your current notification preferences:",
                color=CYBER_THEME_COLOR,
            )

            def status(val):
                return "✅ Enabled" if val else "❌ Disabled"

            embed.add_field(
                name="1 Hour Reminder",
                value=status(settings.get("reminder_1h_before", 1)),
                inline=True
            )
            embed.add_field(
                name="Good Luck Message",
                value=status(settings.get("good_luck_on_start", 1)),
                inline=True
            )
            embed.add_field(
                name="Ending Soon Alert",
                value=status(settings.get("ending_soon_1h", 1)),
                inline=True
            )
            embed.add_field(
                name="Congratulations Message",
                value=status(settings.get("congratulations_on_end", 1)),
                inline=True
            )
            embed.add_field(
                name="Channel Notifications",
                value=status(settings.get("channel_notification", 1)),
                inline=True
            )
            embed.add_field(
                name="Timezone",
                value=f"`{settings.get('timezone', 'Europe/Paris')}`",
                inline=True
            )

            embed.set_footer(text="Use /notifications with options to change settings")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Update settings
        await database.update_user_notification_settings(
            interaction.user.id,
            reminder_1h=reminder_1h,
            good_luck=good_luck,
            ending_soon=ending_soon,
            congratulations=congratulations,
            channel_notification=channel_notifications
        )

        # Build confirmation message
        changes = []
        if reminder_1h is not None:
            changes.append(f"• 1 Hour Reminder: {'Enabled' if reminder_1h else 'Disabled'}")
        if good_luck is not None:
            changes.append(f"• Good Luck Message: {'Enabled' if good_luck else 'Disabled'}")
        if ending_soon is not None:
            changes.append(f"• Ending Soon Alert: {'Enabled' if ending_soon else 'Disabled'}")
        if congratulations is not None:
            changes.append(f"• Congratulations Message: {'Enabled' if congratulations else 'Disabled'}")
        if channel_notifications is not None:
            changes.append(f"• Channel Notifications: {'Enabled' if channel_notifications else 'Disabled'}")

        embed = discord.Embed(
            title="✅ Settings Updated",
            description="Your notification preferences have been updated:\n\n" + "\n".join(changes),
            color=CYBER_THEME_COLOR,
        )

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"User {interaction.user.id} updated notification settings")

    # --- Server Settings (Admin only) ---
    @app_commands.command(
        name="set_channel",
        description="Set the notification channel for this server (Admin only)."
    )
    @app_commands.describe(
        channel="The channel to receive CTF notifications"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_notification_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Check bot permissions in the channel
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.followup.send(
                f"I don't have permission to send messages or embed links in {channel.mention}!",
                ephemeral=True
            )
            return

        await database.set_notification_channel(interaction.guild.id, channel.id)

        embed = discord.Embed(
            title="✅ Notification Channel Set",
            description=f"CTF notifications will be sent to {channel.mention}",
            color=CYBER_THEME_COLOR,
        )
        embed.add_field(
            name="What gets posted here?",
            value="• 1 hour reminder before CTF starts (mentions participants)",
            inline=False
        )
        embed.set_footer(text="Users can disable channel notifications in their personal settings")

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"Server {interaction.guild.id} set notification channel to {channel.id}")

    @app_commands.command(
        name="remove_channel",
        description="Remove the notification channel for this server (Admin only)."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_notification_channel(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        await database.set_notification_channel(interaction.guild.id, None)

        embed = discord.Embed(
            title="✅ Notification Channel Removed",
            description="Channel notifications have been disabled for this server.",
            color=CYBER_THEME_COLOR,
        )

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"Server {interaction.guild.id} removed notification channel")

    # --- View Current Settings ---
    @app_commands.command(
        name="settings",
        description="View all your current settings."
    )
    async def view_settings(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        settings = await database.get_user_settings(interaction.user.id)

        embed = discord.Embed(
            title=f"⚙️ Settings for {interaction.user.display_name}",
            color=CYBER_THEME_COLOR,
        )

        # Timezone
        embed.add_field(
            name="⏰ Timezone",
            value=f"`{settings.get('timezone', 'Europe/Paris')}`",
            inline=True
        )

        # Notifications
        def status(val):
            return "✅" if val else "❌"

        notif_status = (
            f"{status(settings.get('reminder_1h_before', 1))} 1h Reminder\n"
            f"{status(settings.get('good_luck_on_start', 1))} Good Luck\n"
            f"{status(settings.get('ending_soon_1h', 1))} Ending Soon\n"
            f"{status(settings.get('congratulations_on_end', 1))} Congratulations\n"
            f"{status(settings.get('channel_notification', 1))} Channel Notifs"
        )
        embed.add_field(
            name="🔔 Notifications",
            value=notif_status,
            inline=True
        )

        # Server settings (if in a guild)
        if interaction.guild:
            server_settings = await database.get_server_settings(interaction.guild.id)
            channel_id = server_settings.get("notification_channel_id")
            if channel_id:
                embed.add_field(
                    name="📢 Server Channel",
                    value=f"<#{channel_id}>",
                    inline=True
                )
            else:
                embed.add_field(
                    name="📢 Server Channel",
                    value="Not configured",
                    inline=True
                )

        embed.set_footer(text="Use /timezone, /notifications to modify")
        await interaction.followup.send(embed=embed, ephemeral=True)


# --- Setup Function ---
async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCommands(bot))
