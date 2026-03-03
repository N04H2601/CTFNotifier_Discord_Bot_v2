# main.py

import os
import sys
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- Path Setup ---
# Ensure we can import from the correct directory
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from utils import database, ctftime_api

# --- Configuration ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in environment variables. Create a .env file with DISCORD_TOKEN=your_token")

# Optional: Set GUILD_ID for instant command sync (development)
GUILD_ID = os.getenv("GUILD_ID")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CTFNotifier")

# File handler for persistent logs
log_file = BASE_DIR / "data" / "discord_bot.log"
file_handler = logging.FileHandler(filename=log_file, encoding="utf-8", mode="a")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
)
logging.getLogger().addHandler(file_handler)

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True  # Required for fetching members for teams and threads


class CTFNotifierBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents
        )
        self.synced = False

    async def setup_hook(self):
        # Initialize Database
        await database.initialize_database()
        logger.info("Database initialized.")

        # Load Cogs
        cogs_dir = BASE_DIR / "cogs"
        loaded_cogs = []
        failed_cogs = []

        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(cog_name)
                    loaded_cogs.append(filename)
                    logger.info(f"Loaded cog: {filename}")
                except Exception as e:
                    failed_cogs.append(filename)
                    logger.error(f"Failed to load cog {filename}: {e}", exc_info=True)

        logger.info(f"Cogs loaded: {len(loaded_cogs)}/{len(loaded_cogs) + len(failed_cogs)}")
        if failed_cogs:
            logger.warning(f"Failed cogs: {', '.join(failed_cogs)}")

        # Sync commands
        if GUILD_ID:
            # Instant sync to specific guild (for development)
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Command tree synced to guild {GUILD_ID} (instant)")
        else:
            # Global sync (can take up to 1 hour to propagate)
            await self.tree.sync()
            logger.info("Command tree synced globally (may take up to 1 hour to propagate)")

        self.synced = True

    async def on_ready(self):
        logger.info(f"{self.user} has connected to Discord!")
        logger.info(f"Bot ID: {self.user.id}")
        logger.info(f"Guilds: {len(self.guilds)}")

        # List all registered commands
        commands_list = [cmd.name for cmd in self.tree.get_commands()]
        logger.info(f"Registered commands ({len(commands_list)}): {', '.join(commands_list)}")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="CTF events | /help"
            )
        )

    async def close(self):
        """Cleanup on bot shutdown."""
        logger.info("Bot shutting down, cleaning up...")
        await ctftime_api.close_session()
        await super().close()


bot = CTFNotifierBot()


# --- Global Error Handler for Slash Commands ---
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError
):
    """Global error handler for all slash commands."""
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"This command is on cooldown. Try again in {error.retry_after:.1f}s.",
            ephemeral=True,
        )
    elif isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You don't have permission to use this command.",
            ephemeral=True,
        )
    else:
        logger.error(f"Unhandled command error: {error}", exc_info=error)
        # Try to respond to the user
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "An unexpected error occurred. Please try again later.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "An unexpected error occurred. Please try again later.",
                    ephemeral=True,
                )
        except discord.InteractionResponded:
            pass
        except Exception:
            pass


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    print(f"Starting CTF Notifier Bot...")
    print(f"Base directory: {BASE_DIR}")
    print(f"Guild ID for instant sync: {GUILD_ID or 'Not set (using global sync)'}")
    print("-" * 50)
    asyncio.run(main())
