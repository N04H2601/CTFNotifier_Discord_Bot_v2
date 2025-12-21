# utils/ctftime_api.py

import json
import logging
from datetime import datetime
from typing import Optional

import aiohttp

CTFTIME_API_BASE = "https://ctftime.org/api/v1"
HEADERS = {
    "User-Agent": "CTFNotifierDiscordBot/2.0 (+https://github.com/N04H2601/CTFNotifier_Discord_Bot)"
}
REQUEST_TIMEOUT = 10  # seconds

# Simple in-memory cache with TTL
_cache: dict = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key: str) -> Optional[dict]:
    """Get cached value if not expired."""
    if key in _cache:
        value, timestamp = _cache[key]
        if (datetime.now() - timestamp).total_seconds() < CACHE_TTL_SECONDS:
            logging.debug(f"Cache hit for key: {key}")
            return value
        del _cache[key]
    return None


def _set_cache(key: str, value: dict) -> None:
    """Set cache value with current timestamp."""
    _cache[key] = (value, datetime.now())
    logging.debug(f"Cached value for key: {key}")


def clear_cache() -> None:
    """Clear the entire cache."""
    _cache.clear()
    logging.info("API cache cleared.")


async def fetch_event_details(event_id: int) -> Optional[dict]:
    """Fetches details for a specific event ID from CTFtime API (async)."""
    cache_key = f"event_{event_id}"

    # Check cache first
    cached = _get_cached(cache_key)
    if cached:
        return cached

    url = f"{CTFTIME_API_BASE}/events/{event_id}/"

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(
                        f"HTTP error occurred while fetching event {event_id}: Status {response.status}"
                    )
                    return None

                event_data = await response.json()

        # Basic validation and type conversion
        required_keys = [
            "title",
            "start",
            "finish",
            "ctftime_url",
        ]
        if not all(key in event_data for key in required_keys):
            logging.error(
                f"Missing required keys in CTFtime API response for event ID {event_id}"
            )
            return None

        # Parse dates safely
        try:
            event_data["start"] = datetime.fromisoformat(event_data["start"])
            event_data["finish"] = datetime.fromisoformat(event_data["finish"])
        except (ValueError, TypeError) as e:
            logging.error(f"Error parsing dates for event ID {event_id}: {e}")
            return None

        # Clean up organizers list
        if isinstance(event_data.get("organizers"), list):
            event_data["organizers"] = ", ".join(
                [o.get("name", "Unknown") for o in event_data["organizers"]]
            )
        else:
            event_data["organizers"] = event_data.get("organizers", "Unknown")

        # Generate a unique-ish name (similar to original logic)
        event_data["event_name"] = (
            event_data["title"]
            .strip()
            .replace(" ", "-")
            .replace('"', "")
            .replace('"', "")
        )

        # Ensure optional fields have defaults
        event_data.setdefault("url", "")
        event_data.setdefault("format", "N/A")
        event_data.setdefault("weight", 0.0)
        event_data.setdefault("description", "")
        event_data.setdefault("participants", 0)

        # Cache the result
        _set_cache(cache_key, event_data)

        return event_data

    except aiohttp.ClientError as e:
        logging.error(f"Client error occurred while fetching event {event_id}: {e}")
    except json.JSONDecodeError as json_err:
        logging.error(f"Error decoding JSON response for event {event_id}: {json_err}")
    except Exception as e:
        logging.error(f"Unexpected error while fetching event {event_id}: {e}", exc_info=True)

    return None


async def fetch_upcoming_events(
    limit: int = 15,
    format_filter: Optional[str] = None,
    min_weight: Optional[float] = None
) -> list:
    """Fetches upcoming events from CTFtime API (async).

    Args:
        limit: Maximum number of events to fetch (default: 15)
        format_filter: Optional filter by format (e.g., "Jeopardy", "Attack-Defense")
        min_weight: Optional minimum weight filter
    """
    cache_key = f"upcoming_{limit}"

    # Check cache first (only for unfiltered requests)
    if not format_filter and not min_weight:
        cached = _get_cached(cache_key)
        if cached:
            return cached

    url = f"{CTFTIME_API_BASE}/events/"
    params = {"limit": limit * 2 if (format_filter or min_weight) else limit}  # Fetch more if filtering

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logging.error(
                        f"HTTP error occurred while fetching upcoming events: Status {response.status}"
                    )
                    return []

                events_list = await response.json()

        processed_events = []
        for event in events_list:
            try:
                # Basic validation
                if not all(
                    k in event for k in ["title", "start", "finish", "ctftime_url"]
                ):
                    logging.warning(
                        f"Skipping upcoming event due to missing keys: {event.get('title', 'N/A')}"
                    )
                    continue

                event["start_dt"] = datetime.fromisoformat(event["start"])
                event["finish_dt"] = datetime.fromisoformat(event["finish"])

                # Apply filters
                if format_filter:
                    event_format = event.get("format", "").lower()
                    if format_filter.lower() not in event_format:
                        continue

                if min_weight is not None:
                    event_weight = event.get("weight", 0.0)
                    if event_weight < min_weight:
                        continue

                processed_events.append(event)

                if len(processed_events) >= limit:
                    break

            except (ValueError, TypeError) as e:
                logging.warning(
                    f"Error processing date for upcoming event {event.get('title', 'N/A')}: {e}"
                )
                continue

        # Cache only unfiltered results
        if not format_filter and not min_weight:
            _set_cache(cache_key, processed_events)

        return processed_events

    except aiohttp.ClientError as e:
        logging.error(f"Client error occurred while fetching upcoming events: {e}")
    except json.JSONDecodeError as json_err:
        logging.error(f"Error decoding JSON response for upcoming events: {json_err}")
    except Exception as e:
        logging.error(f"Unexpected error while fetching upcoming events: {e}", exc_info=True)

    return []


async def search_events(query: str, limit: int = 10) -> list:
    """Search for events by name/keyword.

    Note: CTFtime API doesn't have a search endpoint, so we fetch upcoming
    events and filter locally. For past events, we'd need to implement
    additional logic or use web scraping.
    """
    # Fetch more events to have a better chance of finding matches
    all_events = await fetch_upcoming_events(limit=100)

    query_lower = query.lower()
    matches = []

    for event in all_events:
        title = event.get("title", "").lower()
        if query_lower in title:
            matches.append(event)
            if len(matches) >= limit:
                break

    return matches
