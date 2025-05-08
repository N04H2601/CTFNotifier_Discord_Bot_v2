# utils/helpers.py

from datetime import datetime
import pytz


def format_discord_timestamp(dt: datetime, style: str = "F") -> str:
    """Formats a datetime object into a Discord timestamp string.

    Args:
        dt: The datetime object (must be timezone-aware, preferably UTC).
        style: Discord timestamp style (e.g., 'f', 'F', 'd', 'D', 't', 'T', 'R').
               Defaults to 'F' (Long Date/Time).

    Returns:
        A Discord timestamp string (e.g., '<t:1678886400:F>').
    """
    if dt.tzinfo is None:
        # Attempt to localize if naive, assuming UTC is the intended base
        dt = pytz.utc.localize(dt)
    else:
        # Ensure it's UTC before getting timestamp
        dt = dt.astimezone(pytz.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"
