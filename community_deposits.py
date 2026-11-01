#!/usr/bin/env python3

"""Client helpers for the ED Alliance Community Deposits API."""

import json

import requests
import app_settings
from edmc_plugin.EDHF_Community_Navigator.api_credentials import get_api_key


API_BASE = "https://ed-alliance-community-deposits.littlejacket99.workers.dev"
DEPOSITS_URL = f"{API_BASE}/v1/deposits"
USER_AGENT = "ED-Hotspots-Finder-Rings-and-Planets/1.0.4"
REQUEST_TIMEOUT = 20

COMMUNITY_HEADERS = [
    "System",
    "Body",
    "Location",
    "Commodity",
    "Rigs",
    "Amount",
    "Density",
    "Depleted at",
    "Latitude",
    "Longitude",
    "Reports",
    "Updated",
]


class CommunityDepositsError(RuntimeError):
    pass


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        from finder_engine import ScanCancelled

        raise ScanCancelled("Scan cancelled by user.")


def _read_api_key(commander=None):
    profile = commander
    if not profile:
        settings = app_settings.load_settings()
        profile = settings.get("community_api", {}).get("commander", "")
    key = get_api_key(profile) if profile else None
    if not key:
        raise CommunityDepositsError(
            "Configure a Community Deposits API key for the commander in Settings."
        )
    return key


def _cell_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _first_value(item, keys, default=""):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return _cell_value(value)
    return default


def _format_depleted_at(value):
    if value in (None, ""):
        return "Active"

    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]

    # Display Community Deposits timestamps consistently with Updated:
    # YYYY-MM-DD HH:MM:SS. Keep the full value in the API/database.
    if len(text) >= 19:
        return text[:19]
    return text


def _normalise_rows(raw_rows, requested_system=None):
    """Return only user-facing Community Deposits columns."""

    rows = []

    for item in raw_rows:
        if not isinstance(item, dict):
            continue

        row = {
            "System": _first_value(
                item,
                ("system", "system_name", "star_system"),
                requested_system or "",
            ),
            "Body": _first_value(
                item,
                ("body", "body_name", "planet_name"),
            ),
            "Location": _first_value(
                item,
                ("location_index", "location"),
            ),
            "Commodity": _first_value(
                item,
                ("commodity", "material"),
            ),
            "Rigs": _first_value(item, ("rigs",)),
            "Amount": _first_value(item, ("amount",)),
            "Density": _first_value(item, ("density",)),
            "Depleted at": _format_depleted_at(
                item.get("depleted_at"),
            ),
            "Latitude": _first_value(item, ("latitude", "lat")),
            "Longitude": _first_value(item, ("longitude", "lon", "lng")),
            "Reports": _first_value(
                item,
                ("report_count", "reports_count", "reports"),
            ),
            "Updated": _first_value(
                item,
                ("updated_at", "last_reported_at", "last_seen_at"),
            ),
        }
        rows.append(row)

    return list(COMMUNITY_HEADERS), rows


def _validate_payload(response, *, context):
    if response.status_code != 200:
        raise CommunityDepositsError(
            f"Community Deposits API returned HTTP {response.status_code} "
            f"for {context}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise CommunityDepositsError(
            f"Community Deposits API returned invalid JSON for {context}."
        ) from exc

    if not isinstance(payload, dict):
        raise CommunityDepositsError(
            f"Community Deposits API returned an unexpected response for {context}."
        )

    if payload.get("status") not in (None, "ok"):
        raise CommunityDepositsError(
            f"Community Deposits API returned an error for {context}."
        ) from None

    deposits = payload.get("deposits", [])
    if deposits is None:
        deposits = []
    if not isinstance(deposits, list):
        raise CommunityDepositsError(
            f"Community Deposits API returned invalid deposits data for {context}."
        )

    return deposits


def fetch_all_deposits(*, cancel_event=None, commander=None):
    """Fetch every Community Deposit currently exposed by the API."""

    _check_cancel(cancel_event)

    api_key = _read_api_key(commander)
    try:
        response = requests.get(
            DEPOSITS_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                     "Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise CommunityDepositsError(
            "Community Deposits request failed due to a network error."
        ) from None

    _check_cancel(cancel_event)
    deposits = _validate_payload(response, context="all deposits")
    return _normalise_rows(deposits)


def fetch_system_deposits(system, *, session=None, cancel_event=None, commander=None):
    _check_cancel(cancel_event)

    system = str(system or "").strip()
    if not system:
        return list(COMMUNITY_HEADERS), []

    api_key = _read_api_key(commander)
    client = session or requests.Session()
    try:
        response = client.get(
            DEPOSITS_URL,
            params={"system": system},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                     "Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise CommunityDepositsError(
            f"Community Deposits request failed for {system} due to a network error."
        ) from None

    _check_cancel(cancel_event)
    deposits = _validate_payload(response, context=system)
    return _normalise_rows(deposits, requested_system=system)


def fetch_deposits_for_systems(systems, *, cancel_event=None, commander=None):
    """Fetch Community Deposits for each selected system."""

    all_rows = []

    with requests.Session() as session:
        for system in systems:
            _check_cancel(cancel_event)
            _headers, rows = fetch_system_deposits(
                system,
                session=session,
                cancel_event=cancel_event,
                commander=commander,
            )
            all_rows.extend(rows)

    return list(COMMUNITY_HEADERS), all_rows
