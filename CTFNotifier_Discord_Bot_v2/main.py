# main.py

import os
import asyncio
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils import database

# --- Configuration ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not loaded")
# CHANNEL_ID is no longer needed globally, notifications will be handled differently
# GUILD_ID = discord.Object(id=int(os.getenv("GUILD_ID"))) # Optional: If you want commands synced to one guild instantly

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s: %(message)s"
)
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)  # Set discord logger level
handler = logging.FileHandler(filename="discord_bot.log", encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

# --- Bot Setup ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
# No message content intent needed for slash commands primarily
# intents.message_content = True # Keep if you need on_message for other things


class CTFNotifierBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"), intents=intents
        )  # Prefix is fallback, not primary

    async def setup_hook(self):
        # Initialize Database
        await database.initialize_database()
        logger.info("Database initialized.")

        # Load Cogs
        cogs_dir = "cogs"
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    logger.info(f"Loaded cog: {filename}")
                except Exception as e:
                    logger.error(f"Failed to load cog {filename}: {e}", exc_info=True)

        # Sync commands globally (can take up to an hour)
        # To sync instantly to one guild, uncomment GUILD_ID and use:
        # self.tree.copy_global_to(guild=GUILD_ID)
        # await self.tree.sync(guild=GUILD_ID)
        await self.tree.sync()
        logger.info("Command tree synced.")

    async def on_ready(self):
        logger.info(f"{self.user} has connected to Discord!")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="upcoming CTF events"
            )
        )
        logger.info("Bot presence set.")

    # Remove the old on_message listener if not needed
    # async def on_message(self, message):
    #     if message.author == self.user:
    #         return
    #     # Handle non-command messages if necessary
    #     await self.process_commands(message) # Keep if using prefix commands too


bot = CTFNotifierBot()


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    if TOKEN is None:
        print("Error: DISCORD_TOKEN environment variable not set.")
    else:
        asyncio.run(main())
