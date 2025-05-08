# utils/ctftime_api.py

import requests
import logging
from datetime import datetime

CTFTIME_API_BASE = "https://ctftime.org/api/v1"
HEADERS = {
    "User-Agent": "CTFNotifierDiscordBot/1.0 (+https://github.com/N04H2601/CTFNotifier_Discord_Bot - Improvement by Manus)"
}
REQUEST_TIMEOUT = 10  # seconds


def fetch_event_details(event_id: int):
    """Fetches details for a specific event ID from CTFtime API."""
    url = f"{CTFTIME_API_BASE}/events/{event_id}/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        event_data = response.json()

        # Basic validation and type conversion
        required_keys = [
            "title",
            "start",
            "finish",
            "ctftime_url",
            "url",
            "format",
            "organizers",
            "weight",
            "description",
            "participants",
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
            event_data["organizers"] = "Unknown"

        # Generate a unique-ish name (similar to original logic)
        event_data["event_name"] = (
            event_data["title"]
            .strip()
            .replace(" ", "-")
            .replace('"', "")
            .replace('"', "")
        )

        return event_data

    except requests.exceptions.HTTPError as http_err:
        logging.error(
            f"HTTP error occurred while fetching event {event_id}: {http_err} - Status: {http_err.response.status_code}"
        )
    except requests.exceptions.ConnectionError as conn_err:
        logging.error(
            f"Connection error occurred while fetching event {event_id}: {conn_err}"
        )
    except requests.exceptions.Timeout as timeout_err:
        logging.error(
            f"Timeout error occurred while fetching event {event_id}: {timeout_err}"
        )
    except requests.exceptions.RequestException as req_err:
        logging.error(
            f"An unexpected error occurred while fetching event {event_id}: {req_err}"
        )
    except json.JSONDecodeError as json_err:
        logging.error(f"Error decoding JSON response for event {event_id}: {json_err}")

    return None


def fetch_upcoming_events(limit: int = 15):
    """Fetches upcoming events from CTFtime API."""
    url = f"{CTFTIME_API_BASE}/events/"
    params = {"limit": limit}
    try:
        response = requests.get(
            url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        events_list = response.json()

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
                processed_events.append(event)
            except (ValueError, TypeError) as e:
                logging.warning(
                    f"Error processing date for upcoming event {event.get('title', 'N/A')}: {e}"
                )
                continue

        return processed_events

    except requests.exceptions.HTTPError as http_err:
        logging.error(
            f"HTTP error occurred while fetching upcoming events: {http_err} - Status: {http_err.response.status_code}"
        )
    except requests.exceptions.ConnectionError as conn_err:
        logging.error(
            f"Connection error occurred while fetching upcoming events: {conn_err}"
        )
    except requests.exceptions.Timeout as timeout_err:
        logging.error(
            f"Timeout error occurred while fetching upcoming events: {timeout_err}"
        )
    except requests.exceptions.RequestException as req_err:
        logging.error(
            f"An unexpected error occurred while fetching upcoming events: {req_err}"
        )
    except json.JSONDecodeError as json_err:
        logging.error(f"Error decoding JSON response for upcoming events: {json_err}")

    return []  # Return empty list on error


# Import json for JSONDecodeError handling
import json
