# CTFNotifier Discord Bot (Improved)

This is an enhanced version of a Discord bot designed to help users track Capture The Flag (CTF) events. Originally a personal project from April 2023, this version introduces significant improvements including personal agendas, slash commands, a modular structure, and a refined notification system.

## ✨ Features

*   **Personal Agendas:** Each user manages their own list of CTF events.
*   **CTFtime Integration:** Add events directly using their CTFtime URL and view upcoming events.
*   **Slash Commands:** Modern and easy-to-use interface via Discord's slash commands.
*   **Automated Notifications:** Receive Direct Messages (DMs) for event reminders (1 hour before start), start times, and when events are ending soon (1 hour before finish).
*   **SQLite Database:** Events are persistently stored in a local SQLite database.
*   **Modular Codebase:** Organized using Discord.py Cogs for better maintainability.
*   **Cybersecurity Theme:** Embeds use a consistent color scheme.

## 📁 Project Structure

```
CTFNotifier_Discord_Bot/
├── cogs/                 # Contains command and event handler modules (Cogs)
│   ├── event_commands.py
│   ├── general_commands.py
│   └── notification_service.py
├── data/                 # Stores persistent data
│   └── ctf_data.db       # SQLite database for user events
├── utils/                # Utility modules
│   ├── ctftime_api.py    # Functions for interacting with CTFtime API
│   └── database.py       # Functions for database operations
├── .env                  # Environment variables (TOKEN, etc.) - You need to create this!
├── main.py               # Main bot entry point
├── requirements.txt      # Python dependencies
├── data/                 # Runtime data (logs + database, auto-created)
│   ├── ctf_data.db
│   └── discord_bot.log
└── README.md             # This file
```

## 🚀 Setup & Installation

### Option 1: Python (direct)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/N04H2601/CTFNotifier_Discord_Bot.git
    cd CTFNotifier_Discord_Bot
    ```

2.  **Python Version:**
    This bot was developed and tested using Python 3.11+. Ensure you have a compatible Python version installed.

3.  **Create Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment Variables:**
    Create a file named `.env` in the project's root directory. Add your Discord Bot Token to it:
    ```dotenv
    DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
    # Optional: For faster command syncing during testing/development in a single server
    # GUILD_ID=YOUR_TEST_SERVER_ID_HERE
    ```
    Replace `YOUR_BOT_TOKEN_HERE` with your actual bot token obtained from the Discord Developer Portal.

6.  **Run the Bot:**
    ```bash
    python main.py
    ```
    The bot should connect to Discord, initialize the database, load commands, and start the notification service.

### Option 2: Docker

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/N04H2601/CTFNotifier_Discord_Bot.git
    cd CTFNotifier_Discord_Bot
    ```

2.  **Configure Environment Variables:**
    Create a `.env` file at the project root:
    ```dotenv
    DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
    # GUILD_ID=YOUR_TEST_SERVER_ID_HERE
    ```

3.  **Build the Docker image:**
    ```bash
    docker build -t ctfnotifier-bot .
    ```

4.  **Run the container:**
    ```bash
    docker run -d \
      --name ctfnotifier \
      --env-file .env \
      --volume ctfnotifier-data:/app/data \
      --restart unless-stopped \
      ctfnotifier-bot
    ```

    The `--volume` flag persists the database and logs across container restarts.
    The `.env` file is **not** baked into the image (excluded by `.dockerignore`).

## 🤖 Commands (Slash Commands)

Use these commands directly in Discord by typing `/`:

*   `/add <ctftime_url>`: Adds a CTF event to your personal agenda using its CTFtime event URL (e.g., `https://ctftime.org/event/1234`).
*   `/agenda`: Displays all the upcoming CTF events currently in your personal agenda.
*   `/details <event_name>`: Shows detailed information about a specific event from your agenda. Use the autocomplete feature to find event names easily.
*   `/remove <event_name>`: Removes a specific event from your personal agenda. Use the autocomplete feature.
*   `/clear`: Removes **ALL** events from your personal agenda after confirmation.
*   `/upcoming [limit]`: Shows a list of upcoming CTF events directly from CTFtime (default limit: 10, max: 25).
*   `/ctf_info <query>`: (Experimental) Tries to find basic info about a CTF by name or URL. (Currently under development).

## 🔔 Notifications

The bot automatically checks your added events and sends you DMs for:

*   **1 Hour Reminder:** ~1 hour before the event starts.
*   **Event Start:** When the event begins.
*   **Ending Soon:** ~1 hour before the event finishes.

Ensure your Discord settings allow DMs from server members for the bot to send you notifications.

## 💾 Database

User event data is stored locally in `/data/ctf_data.db`. This file will be created automatically when the bot first starts.

## 💡 Notes & Future Ideas

*   **Raspberry Pi:** The bot is designed to be lightweight and should run on a Raspberry Pi. Resource usage will depend on the number of users and tracked events.
*   **AI Integration:** The `/ctf_info` command is a placeholder. Future development could involve using AI to extract CTF categories (web, pwn, crypto, etc.) from event descriptions or websites.
*   **Timezones:** All event times are currently handled and displayed in UTC.
*   **Error Handling:** Basic error handling is included, and logs are written to `data/discord_bot.log`.

