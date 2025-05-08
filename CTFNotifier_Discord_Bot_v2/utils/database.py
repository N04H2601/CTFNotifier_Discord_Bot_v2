# utils/database.py

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent  # <project root>
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # create it if missing

DATABASE_PATH = DATA_DIR / "ctf_data.db"


async def initialize_database():
    """Initializes the SQLite database and creates tables if they don't exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS user_events (
                user_id INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                ctftime_url TEXT,
                event_url TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                format TEXT,
                organizers TEXT,
                weight REAL,
                description TEXT,
                participants INTEGER,
                reminder_sent INTEGER DEFAULT 0,      -- Boolean (0=False, 1=True)
                good_luck_sent INTEGER DEFAULT 0,   -- Boolean (0=False, 1=True)
                ending_soon_sent INTEGER DEFAULT 0, -- Boolean (0=False, 1=True)
                congratulations_sent INTEGER DEFAULT 0, -- Boolean (0=False, 1=True)
                PRIMARY KEY (user_id, event_name)
            )"""
        )
        await db.commit()
        logging.info("Database initialized successfully.")


async def add_event_to_user(user_id: int, event_data: dict):
    """Adds a CTF event to a specific user's agenda."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO user_events (
                    user_id, event_name, ctftime_url, event_url, start_time, end_time,
                    format, organizers, weight, description, participants
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    user_id,
                    event_data["event_name"],
                    event_data.get("ctftime_url"),
                    event_data.get("url"),
                    event_data["start"],
                    event_data["finish"],
                    event_data.get("format"),
                    event_data.get("organizers"),
                    event_data.get("weight"),
                    event_data.get("description"),
                    event_data.get("participants"),
                ),
            )
            await db.commit()
            logging.info(
                f"Event '{event_data['event_name']}' added for user {user_id}."
            )
            return True
        except aiosqlite.IntegrityError:
            logging.warning(
                f"Event '{event_data['event_name']}' already exists for user {user_id}."
            )
            return False  # Event already exists for this user


async def get_user_events(user_id: int):
    """Retrieves all events for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_events WHERE user_id = ? ORDER BY start_time ASC",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_event_details(user_id: int, event_name: str):
    """Retrieves details for a specific event for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_events WHERE user_id = ? AND event_name = ?",
            (user_id, event_name),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def remove_event_from_user(user_id: int, event_name: str):
    """Removes a specific event from a user's agenda."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM user_events WHERE user_id = ? AND event_name = ?",
            (user_id, event_name),
        )
        await db.commit()
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logging.info(f"Event '{event_name}' removed for user {user_id}.")
        else:
            logging.warning(
                f"Attempted to remove non-existent event '{event_name}' for user {user_id}."
            )
        return deleted_count > 0


async def clear_user_events(user_id: int):
    """Removes all events for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM user_events WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        deleted_count = cursor.rowcount
        logging.info(f"Cleared {deleted_count} events for user {user_id}.")
        return deleted_count


async def get_all_events_for_notifications():
    """Retrieves all events from all users for notification processing."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_events ORDER BY user_id, start_time ASC"
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def update_notification_flag(
    user_id: int, event_name: str, flag_name: str, value: bool
):
    """Updates a specific notification flag for an event."""
    if flag_name not in [
        "reminder_sent",
        "good_luck_sent",
        "ending_soon_sent",
        "congratulations_sent",
    ]:
        raise ValueError("Invalid flag name")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE user_events SET {flag_name} = ? WHERE user_id = ? AND event_name = ?",
            (int(value), user_id, event_name),
        )
        await db.commit()
        logging.debug(
            f"Updated flag '{flag_name}' to {value} for event '{event_name}', user {user_id}."
        )


async def remove_past_events():
    """Removes events that have already finished from the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Remove events that finished more than, say, 1 day ago to avoid race conditions with notifications
        cutoff_time = datetime.utcnow() - timedelta(days=1)
        cursor = await db.execute(
            "DELETE FROM user_events WHERE end_time < ?", (cutoff_time,)
        )
        await db.commit()
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logging.info(f"Removed {deleted_count} past events from the database.")
        return deleted_count


# Add timedelta import
from datetime import timedelta
