from __future__ import annotations

from typing import Any

import requests

from .api_credentials import get_api_key


API_BASE = "https://ed-alliance-community-deposits.littlejacket99.workers.dev"
DEPOSITS_URL = f"{API_BASE}/v1/deposits"
BATCH_URL = f"{API_BASE}/v1/deposits/batch"
REQUEST_TIMEOUT = 20
MAX_BATCH_SIZE = 200
USER_AGENT = "Hotspots-Finder-Deposits-Companion/1.0.4"


class CommunityAPIError(RuntimeError):
    """Raised when the Community Deposits API cannot satisfy a request."""


def _response_json(response: requests.Response, *, context: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise CommunityAPIError(
            f"Community Deposits API returned HTTP {response.status_code} "
            f"for {context}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise CommunityAPIError(
            f"Community Deposits API returned invalid JSON for {context}."
        ) from exc

    if not isinstance(payload, dict):
        raise CommunityAPIError(
            f"Community Deposits API returned an unexpected response for {context}."
        )

    if payload.get("status") not in (None, "ok"):
        raise CommunityAPIError(
            f"Community Deposits API returned an error for {context}."
        ) from None

    return payload


def fetch_system_deposits(system: str, *, commander: str) -> list[dict[str, Any]]:
    system = str(system or "").strip()
    if not system:
        return []

    api_key = get_api_key(commander)
    if not api_key:
        raise CommunityAPIError(
            "Configure a Community Deposits API key in the plugin settings."
        )
    try:
        response = requests.get(
            DEPOSITS_URL,
            params={"system": system},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                     "Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise CommunityAPIError(
            f"Community Deposits request failed for {system} due to a network error."
        ) from None

    payload = _response_json(response, context=system)
    deposits = payload.get("deposits", [])
    if deposits is None:
        return []
    if not isinstance(deposits, list):
        raise CommunityAPIError(
            f"Community Deposits API returned invalid deposits data for {system}."
        )

    return [item for item in deposits if isinstance(item, dict)]


def send_deposit_batch(
    deposits: list[dict[str, Any]], *, api_key: str | None = None
) -> dict[str, Any]:
    if not deposits:
        return {"results": []}

    if not api_key:
        commanders = {
            str(item.get("commander") or "").strip()
            for item in deposits
            if isinstance(item, dict) and str(item.get("commander") or "").strip()
        }
        if len(commanders) != 1:
            raise CommunityAPIError(
                "An API key is required for the bookmark commander."
            )
        api_key = get_api_key(next(iter(commanders)))
    if not api_key:
        raise CommunityAPIError(
            "No API key is configured for the bookmark commander."
        )
    try:
        response = requests.post(
            BATCH_URL,
            json={"deposits": deposits},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                     "Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except requests.RequestException:
        raise CommunityAPIError(
            "Community Deposits batch upload failed due to a network error."
        ) from None

    return _response_json(response, context="RhinoSpotter batch upload")


def chunks(items: list[dict[str, Any]], size: int = MAX_BATCH_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]
