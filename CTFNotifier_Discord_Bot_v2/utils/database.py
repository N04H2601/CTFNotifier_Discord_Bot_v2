# utils/database.py

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent  # <project root>
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "ctf_data.db"

# Default timezone
DEFAULT_TIMEZONE = "Europe/Paris"


async def initialize_database():
    """Initializes the SQLite database and creates tables if they don't exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # User settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT DEFAULT 'Europe/Paris',
                reminder_1h_before INTEGER DEFAULT 1,
                good_luck_on_start INTEGER DEFAULT 1,
                ending_soon_1h INTEGER DEFAULT 1,
                congratulations_on_end INTEGER DEFAULT 1,
                channel_notification INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Server settings table (for notification channel)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                server_id INTEGER PRIMARY KEY,
                notification_channel_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Events table (central event storage - not deleted after end for writeups)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                ctftime_url TEXT,
                ctftime_id INTEGER,
                event_url TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                format TEXT,
                organizers TEXT,
                weight REAL DEFAULT 0.0,
                description TEXT,
                participants INTEGER DEFAULT 0,
                is_custom INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # User events (link between users and events they're participating in)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                server_id INTEGER,
                reminder_sent INTEGER DEFAULT 0,
                good_luck_sent INTEGER DEFAULT 0,
                ending_soon_sent INTEGER DEFAULT 0,
                congratulations_sent INTEGER DEFAULT 0,
                channel_reminder_sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                UNIQUE(user_id, event_id)
            )
        """)

        # Event members (team members for each event - for group participation)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                member_user_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                UNIQUE(event_id, owner_user_id, member_user_id)
            )
        """)

        # Writeups table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS writeups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT,
                url TEXT NOT NULL,
                challenge_name TEXT,
                category TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            )
        """)

        # Create indexes for better performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_events_user ON user_events(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_events_event ON user_events(event_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_time)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_end ON events(end_time)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_event_members_event ON event_members(event_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_writeups_event ON writeups(event_id)")

        await db.commit()
        logging.info("Database initialized successfully with new schema.")


# =====================
# USER SETTINGS
# =====================

async def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Get user settings, creating defaults if not exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        # Create default settings
        await db.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()
        return {
            "user_id": user_id,
            "timezone": DEFAULT_TIMEZONE,
            "reminder_1h_before": 1,
            "good_luck_on_start": 1,
            "ending_soon_1h": 1,
            "congratulations_on_end": 1,
            "channel_notification": 1,
        }


async def update_user_timezone(user_id: int, timezone: str) -> bool:
    """Update user's timezone."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await get_user_settings(user_id)  # Ensure user exists
        await db.execute(
            "UPDATE user_settings SET timezone = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (timezone, user_id)
        )
        await db.commit()
        return True


async def update_user_notification_settings(
    user_id: int,
    reminder_1h: Optional[bool] = None,
    good_luck: Optional[bool] = None,
    ending_soon: Optional[bool] = None,
    congratulations: Optional[bool] = None,
    channel_notification: Optional[bool] = None
) -> bool:
    """Update user's notification preferences."""
    await get_user_settings(user_id)  # Ensure user exists

    updates = []
    values = []

    if reminder_1h is not None:
        updates.append("reminder_1h_before = ?")
        values.append(int(reminder_1h))
    if good_luck is not None:
        updates.append("good_luck_on_start = ?")
        values.append(int(good_luck))
    if ending_soon is not None:
        updates.append("ending_soon_1h = ?")
        values.append(int(ending_soon))
    if congratulations is not None:
        updates.append("congratulations_on_end = ?")
        values.append(int(congratulations))
    if channel_notification is not None:
        updates.append("channel_notification = ?")
        values.append(int(channel_notification))

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(user_id)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE user_settings SET {', '.join(updates)} WHERE user_id = ?",
            tuple(values)
        )
        await db.commit()
        return True


# =====================
# SERVER SETTINGS
# =====================

async def get_server_settings(server_id: int) -> Dict[str, Any]:
    """Get server settings."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM server_settings WHERE server_id = ?", (server_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return {"server_id": server_id, "notification_channel_id": None}


async def set_notification_channel(server_id: int, channel_id: Optional[int]) -> bool:
    """Set the notification channel for a server."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO server_settings (server_id, notification_channel_id)
            VALUES (?, ?)
            ON CONFLICT(server_id) DO UPDATE SET
                notification_channel_id = excluded.notification_channel_id,
                updated_at = CURRENT_TIMESTAMP
        """, (server_id, channel_id))
        await db.commit()
        return True


# =====================
# EVENTS
# =====================

async def get_or_create_event(event_data: dict) -> Optional[int]:
    """Get existing event or create new one. Returns event ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check if event already exists
        async with db.execute(
            "SELECT id FROM events WHERE event_name = ?",
            (event_data["event_name"],)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row["id"]

        # Create new event
        try:
            cursor = await db.execute("""
                INSERT INTO events (
                    event_name, title, ctftime_url, ctftime_id, event_url,
                    start_time, end_time, format, organizers, weight,
                    description, participants, is_custom, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data["event_name"],
                event_data.get("title", event_data["event_name"]),
                event_data.get("ctftime_url"),
                event_data.get("ctftime_id"),
                event_data.get("url"),
                event_data["start"],
                event_data["finish"],
                event_data.get("format"),
                event_data.get("organizers"),
                event_data.get("weight", 0.0),
                event_data.get("description"),
                event_data.get("participants", 0),
                event_data.get("is_custom", 0),
                event_data.get("created_by"),
            ))
            await db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            logging.warning(f"Event '{event_data['event_name']}' already exists.")
            return None


async def add_event_to_user(user_id: int, event_data: dict, server_id: Optional[int] = None) -> bool:
    """Adds a CTF event to a specific user's agenda."""
    event_id = await get_or_create_event(event_data)
    if not event_id:
        return False

    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO user_events (user_id, event_id, server_id)
                VALUES (?, ?, ?)
            """, (user_id, event_id, server_id))
            await db.commit()
            logging.info(f"Event '{event_data['event_name']}' added for user {user_id}.")
            return True
        except aiosqlite.IntegrityError:
            logging.warning(f"Event already in user {user_id}'s agenda.")
            return False


async def get_user_events(user_id: int, include_past: bool = False) -> List[Dict]:
    """Retrieves all events for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        if include_past:
            query = """
                SELECT e.*, ue.reminder_sent, ue.good_luck_sent,
                       ue.ending_soon_sent, ue.congratulations_sent, ue.server_id
                FROM events e
                JOIN user_events ue ON e.id = ue.event_id
                WHERE ue.user_id = ?
                ORDER BY e.start_time ASC
            """
        else:
            query = """
                SELECT e.*, ue.reminder_sent, ue.good_luck_sent,
                       ue.ending_soon_sent, ue.congratulations_sent, ue.server_id
                FROM events e
                JOIN user_events ue ON e.id = ue.event_id
                WHERE ue.user_id = ? AND e.end_time >= datetime('now')
                ORDER BY e.start_time ASC
            """

        async with db.execute(query, (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_past_events(user_id: int, limit: int = 50) -> List[Dict]:
    """Retrieves past events for a specific user (for stats and writeups)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.*, ue.server_id
            FROM events e
            JOIN user_events ue ON e.id = ue.event_id
            WHERE ue.user_id = ? AND e.end_time < datetime('now')
            ORDER BY e.end_time DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_event_by_name(event_name: str) -> Optional[Dict]:
    """Get event by its name."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM events WHERE event_name = ?", (event_name,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_event_by_id(event_id: int) -> Optional[Dict]:
    """Get event by its ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_event_details(user_id: int, event_name: str) -> Optional[Dict]:
    """Retrieves details for a specific event for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.*, ue.reminder_sent, ue.good_luck_sent,
                   ue.ending_soon_sent, ue.congratulations_sent, ue.server_id
            FROM events e
            JOIN user_events ue ON e.id = ue.event_id
            WHERE ue.user_id = ? AND e.event_name = ?
        """, (user_id, event_name)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def remove_event_from_user(user_id: int, event_name: str) -> bool:
    """Removes a specific event from a user's agenda (keeps event in events table)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        event = await get_event_by_name(event_name)
        if not event:
            return False

        cursor = await db.execute(
            "DELETE FROM user_events WHERE user_id = ? AND event_id = ?",
            (user_id, event["id"])
        )
        await db.commit()
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logging.info(f"Event '{event_name}' removed from user {user_id}'s agenda.")
        return deleted_count > 0


async def clear_user_events(user_id: int) -> int:
    """Removes all events from a specific user's agenda."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM user_events WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        deleted_count = cursor.rowcount
        logging.info(f"Cleared {deleted_count} events from user {user_id}'s agenda.")
        return deleted_count


async def search_user_events(user_id: int, query: str) -> List[Dict]:
    """Search events in user's agenda by name or description."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        search_pattern = f"%{query}%"
        async with db.execute("""
            SELECT e.*, ue.server_id
            FROM events e
            JOIN user_events ue ON e.id = ue.event_id
            WHERE ue.user_id = ? AND (
                e.event_name LIKE ? OR
                e.title LIKE ? OR
                e.description LIKE ? OR
                e.organizers LIKE ?
            )
            ORDER BY e.start_time ASC
        """, (user_id, search_pattern, search_pattern, search_pattern, search_pattern)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# =====================
# EVENT MEMBERS (TEAMS)
# =====================

async def add_event_member(event_id: int, owner_user_id: int, member_user_id: int) -> bool:
    """Add a member to an event team."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO event_members (event_id, owner_user_id, member_user_id)
                VALUES (?, ?, ?)
            """, (event_id, owner_user_id, member_user_id))
            await db.commit()
            logging.info(f"Added member {member_user_id} to event {event_id} (owner: {owner_user_id})")
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_event_member(event_id: int, owner_user_id: int, member_user_id: int) -> bool:
    """Remove a member from an event team."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM event_members
            WHERE event_id = ? AND owner_user_id = ? AND member_user_id = ?
        """, (event_id, owner_user_id, member_user_id))
        await db.commit()
        return cursor.rowcount > 0


async def get_event_members(event_id: int, owner_user_id: int) -> List[int]:
    """Get all members of an event team."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("""
            SELECT member_user_id FROM event_members
            WHERE event_id = ? AND owner_user_id = ?
        """, (event_id, owner_user_id)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_all_event_participants(event_id: int) -> List[int]:
    """Get all users participating in an event (owners + members)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Get all users who have this event in their agenda
        async with db.execute("""
            SELECT DISTINCT user_id FROM user_events WHERE event_id = ?
        """, (event_id,)) as cursor:
            users = await cursor.fetchall()

        # Also get all members added to teams for this event
        async with db.execute("""
            SELECT DISTINCT member_user_id FROM event_members WHERE event_id = ?
        """, (event_id,)) as cursor:
            members = await cursor.fetchall()

        all_users = set([u[0] for u in users] + [m[0] for m in members])
        return list(all_users)


# =====================
# WRITEUPS
# =====================

async def add_writeup(
    event_id: int,
    user_id: int,
    url: str,
    title: Optional[str] = None,
    challenge_name: Optional[str] = None,
    category: Optional[str] = None,
    notes: Optional[str] = None
) -> int:
    """Add a writeup for an event. Returns writeup ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO writeups (event_id, user_id, url, title, challenge_name, category, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (event_id, user_id, url, title, challenge_name, category, notes))
        await db.commit()
        logging.info(f"Writeup added for event {event_id} by user {user_id}")
        return cursor.lastrowid


async def get_event_writeups(event_id: int) -> List[Dict]:
    """Get all writeups for an event."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM writeups WHERE event_id = ?
            ORDER BY created_at DESC
        """, (event_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_writeups(user_id: int, limit: int = 50) -> List[Dict]:
    """Get all writeups by a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT w.*, e.event_name, e.title as event_title
            FROM writeups w
            JOIN events e ON w.event_id = e.id
            WHERE w.user_id = ?
            ORDER BY w.created_at DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def remove_writeup(writeup_id: int, user_id: int) -> bool:
    """Remove a writeup (only if user owns it)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM writeups WHERE id = ? AND user_id = ?",
            (writeup_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


# =====================
# NOTIFICATIONS
# =====================

async def get_all_events_for_notifications() -> List[Dict]:
    """Retrieves all active events from all users for notification processing."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.*, ue.user_id, ue.reminder_sent, ue.good_luck_sent,
                   ue.ending_soon_sent, ue.congratulations_sent,
                   ue.channel_reminder_sent, ue.server_id,
                   us.reminder_1h_before, us.good_luck_on_start,
                   us.ending_soon_1h, us.congratulations_on_end,
                   us.channel_notification
            FROM events e
            JOIN user_events ue ON e.id = ue.event_id
            LEFT JOIN user_settings us ON ue.user_id = us.user_id
            WHERE e.end_time >= datetime('now', '-1 day')
            ORDER BY ue.user_id, e.start_time ASC
        """) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def update_notification_flag(
    user_id: int, event_name: str, flag_name: str, value: bool
) -> bool:
    """Updates a specific notification flag for an event."""
    valid_flags = [
        "reminder_sent",
        "good_luck_sent",
        "ending_soon_sent",
        "congratulations_sent",
        "channel_reminder_sent",
    ]
    if flag_name not in valid_flags:
        raise ValueError(f"Invalid flag name: {flag_name}")

    event = await get_event_by_name(event_name)
    if not event:
        return False

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE user_events SET {flag_name} = ? WHERE user_id = ? AND event_id = ?",
            (int(value), user_id, event["id"])
        )
        await db.commit()
        logging.debug(f"Updated flag '{flag_name}' to {value} for event '{event_name}', user {user_id}.")
        return True


# =====================
# STATISTICS
# =====================

async def get_user_stats(user_id: int) -> Dict[str, Any]:
    """Get user statistics."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Total events participated
        async with db.execute("""
            SELECT COUNT(*) as count FROM user_events WHERE user_id = ?
        """, (user_id,)) as cursor:
            total_events = (await cursor.fetchone())["count"]

        # Past events (completed)
        async with db.execute("""
            SELECT COUNT(*) as count
            FROM user_events ue
            JOIN events e ON ue.event_id = e.id
            WHERE ue.user_id = ? AND e.end_time < datetime('now')
        """, (user_id,)) as cursor:
            past_events = (await cursor.fetchone())["count"]

        # Upcoming events
        async with db.execute("""
            SELECT COUNT(*) as count
            FROM user_events ue
            JOIN events e ON ue.event_id = e.id
            WHERE ue.user_id = ? AND e.start_time > datetime('now')
        """, (user_id,)) as cursor:
            upcoming_events = (await cursor.fetchone())["count"]

        # Total writeups
        async with db.execute("""
            SELECT COUNT(*) as count FROM writeups WHERE user_id = ?
        """, (user_id,)) as cursor:
            total_writeups = (await cursor.fetchone())["count"]

        # Events by format
        async with db.execute("""
            SELECT e.format, COUNT(*) as count
            FROM user_events ue
            JOIN events e ON ue.event_id = e.id
            WHERE ue.user_id = ? AND e.format IS NOT NULL
            GROUP BY e.format
        """, (user_id,)) as cursor:
            format_stats = {row["format"]: row["count"] for row in await cursor.fetchall()}

        # Average weight of events
        async with db.execute("""
            SELECT AVG(e.weight) as avg_weight
            FROM user_events ue
            JOIN events e ON ue.event_id = e.id
            WHERE ue.user_id = ? AND e.weight > 0
        """, (user_id,)) as cursor:
            avg_weight = (await cursor.fetchone())["avg_weight"] or 0

        return {
            "total_events": total_events,
            "past_events": past_events,
            "upcoming_events": upcoming_events,
            "current_events": total_events - past_events - upcoming_events,
            "total_writeups": total_writeups,
            "format_stats": format_stats,
            "average_weight": round(avg_weight, 2),
        }


# =====================
# CLEANUP (Modified - only removes very old events without writeups)
# =====================

async def cleanup_old_events(days_old: int = 365) -> int:
    """Remove events older than X days that have no writeups attached.
    Events with writeups are preserved indefinitely.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cutoff_time = datetime.utcnow() - timedelta(days=days_old)

        # Only delete events that:
        # 1. Ended more than X days ago
        # 2. Have no writeups attached
        # 3. Are not in any user's agenda
        cursor = await db.execute("""
            DELETE FROM events
            WHERE end_time < ?
            AND id NOT IN (SELECT DISTINCT event_id FROM writeups)
            AND id NOT IN (SELECT DISTINCT event_id FROM user_events)
        """, (cutoff_time,))
        await db.commit()
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logging.info(f"Cleaned up {deleted_count} old events from the database.")
        return deleted_count
