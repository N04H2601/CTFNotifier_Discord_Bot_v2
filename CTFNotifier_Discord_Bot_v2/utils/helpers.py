# utils/helpers.py

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz
import uuid
import re

# List of common timezones for autocomplete
COMMON_TIMEZONES = [
    "Europe/Paris",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Amsterdam",
    "Europe/Brussels",
    "Europe/Zurich",
    "Europe/Warsaw",
    "Europe/Moscow",
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "America/Denver",
    "America/Toronto",
    "America/Vancouver",
    "America/Sao_Paulo",
    "America/Mexico_City",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Seoul",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Hong_Kong",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Pacific/Auckland",
    "UTC",
]


def format_discord_timestamp(dt: datetime, style: str = "F") -> str:
    """Formats a datetime object into a Discord timestamp string.

    Args:
        dt: The datetime object (must be timezone-aware, preferably UTC).
        style: Discord timestamp style:
            - 't': Short time (16:20)
            - 'T': Long time (16:20:30)
            - 'd': Short date (20/04/2021)
            - 'D': Long date (20 April 2021)
            - 'f': Short date/time (20 April 2021 16:20)
            - 'F': Long date/time (Tuesday, 20 April 2021 16:20) [DEFAULT]
            - 'R': Relative (2 months ago)

    Returns:
        A Discord timestamp string (e.g., '<t:1678886400:F>').
    """
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    else:
        dt = dt.astimezone(pytz.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"


def format_datetime_local(dt: datetime, timezone_str: str = "Europe/Paris") -> str:
    """Format datetime in a specific timezone."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    try:
        tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Europe/Paris")

    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


def is_valid_timezone(timezone_str: str) -> bool:
    """Check if a timezone string is valid."""
    try:
        pytz.timezone(timezone_str)
        return True
    except pytz.UnknownTimeZoneError:
        return False


def get_timezone_choices(current: str) -> List[str]:
    """Get timezone choices for autocomplete."""
    current_lower = current.lower()
    matches = []

    # First, check common timezones
    for tz in COMMON_TIMEZONES:
        if current_lower in tz.lower():
            matches.append(tz)

    # Then search all timezones if needed
    if len(matches) < 10:
        for tz in pytz.all_timezones:
            if current_lower in tz.lower() and tz not in matches:
                matches.append(tz)
                if len(matches) >= 25:
                    break

    return matches[:25]


def parse_datetime_with_timezone(
    date_str: str,
    time_str: str,
    timezone_str: str = "Europe/Paris"
) -> Optional[datetime]:
    """Parse date and time strings with a specific timezone, return UTC datetime."""
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        tz = pytz.timezone(timezone_str)
        local_dt = tz.localize(dt)
        return local_dt.astimezone(pytz.utc)
    except (ValueError, pytz.UnknownTimeZoneError):
        return None


def generate_ical(events: List[Dict]) -> str:
    """Generate iCal (.ics) content from a list of events.

    Creates a calendar with:
    - Event details (name, description, times)
    - Alarms: 1 hour before and at event start
    - Proper timezone handling
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CTFNotifier Discord Bot//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:CTF Events",
        "X-WR-TIMEZONE:UTC",
    ]

    for event in events:
        # Parse times
        start_time = event.get("start_time") or event.get("start")
        end_time = event.get("end_time") or event.get("finish")

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)

        # Ensure UTC
        if start_time.tzinfo is None:
            start_time = pytz.utc.localize(start_time)
        else:
            start_time = start_time.astimezone(pytz.utc)

        if end_time.tzinfo is None:
            end_time = pytz.utc.localize(end_time)
        else:
            end_time = end_time.astimezone(pytz.utc)

        # Format times for iCal (YYYYMMDDTHHmmssZ)
        start_str = start_time.strftime("%Y%m%dT%H%M%SZ")
        end_str = end_time.strftime("%Y%m%dT%H%M%SZ")

        # Event details
        event_name = event.get("event_name") or event.get("title", "CTF Event")
        title = event.get("title", event_name)
        description = event.get("description", "")
        location = event.get("event_url") or event.get("url") or ""
        ctftime_url = event.get("ctftime_url", "")

        # Build description
        full_description = []
        if description:
            # Clean description for iCal (escape special chars)
            clean_desc = description.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
            full_description.append(clean_desc[:500])  # Limit length
        if ctftime_url:
            full_description.append(f"\\nCTFtime: {ctftime_url}")
        if location:
            full_description.append(f"\\nOfficial: {location}")

        # Generate unique ID
        uid = f"{uuid.uuid4()}@ctfnotifier"

        # Event block
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{start_str}",
            f"DTEND:{end_str}",
            f"SUMMARY:{_escape_ical_text(title)}",
        ])

        if full_description:
            lines.append(f"DESCRIPTION:{''.join(full_description)}")

        if location:
            lines.append(f"URL:{location}")

        # Add organizers if available
        organizers = event.get("organizers", "")
        if organizers and organizers != "Custom Event":
            lines.append(f"ORGANIZER;CN={_escape_ical_text(organizers)}:mailto:noreply@ctftime.org")

        # Alarm 1: 1 hour before
        lines.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT1H",
            "ACTION:DISPLAY",
            f"DESCRIPTION:CTF starts in 1 hour: {_escape_ical_text(title)}",
            "END:VALARM",
        ])

        # Alarm 2: At start time
        lines.extend([
            "BEGIN:VALARM",
            "TRIGGER:PT0M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:CTF starting now: {_escape_ical_text(title)}",
            "END:VALARM",
        ])

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    return "\r\n".join(lines)


def _escape_ical_text(text: str) -> str:
    """Escape special characters for iCal text fields."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace("\n", "\\n")
    text = text.replace(",", "\\,")
    text = text.replace(";", "\\;")
    return text


def calculate_duration(start: datetime, end: datetime) -> str:
    """Calculate and format duration between two datetimes."""
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)

    delta = end - start
    total_hours = delta.total_seconds() / 3600

    if total_hours < 24:
        return f"{int(total_hours)} hours"
    else:
        days = int(total_hours // 24)
        hours = int(total_hours % 24)
        if hours > 0:
            return f"{days} days, {hours} hours"
        return f"{days} days"


def format_weight(weight: float) -> str:
    """Format CTF weight with color indicator."""
    if weight >= 75:
        return f"🔴 {weight:.2f} (High)"
    elif weight >= 50:
        return f"🟠 {weight:.2f} (Medium)"
    elif weight >= 25:
        return f"🟡 {weight:.2f} (Low)"
    elif weight > 0:
        return f"⚪ {weight:.2f} (Very Low)"
    else:
        return "N/A"
