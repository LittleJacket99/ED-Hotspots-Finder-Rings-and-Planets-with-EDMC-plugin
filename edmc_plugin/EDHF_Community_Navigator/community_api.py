from __future__ import annotations

from typing import Any

import requests
import unicodedata

from .api_credentials import get_api_key
from .batch_protocol import BatchHTTPError


API_BASE = "https://ed-alliance-community-deposits.littlejacket99.workers.dev"
DEPOSITS_URL = f"{API_BASE}/v1/deposits"
BATCH_URL = f"{API_BASE}/v1/deposits/batch"
REQUEST_TIMEOUT = 20
MAX_BATCH_SIZE = 5
# Pace distinct batches below the existing 60 writes/minute/key budget.
BATCH_PAUSE_SECONDS = 1.1
USER_AGENT = "Hotspots-Finder-Deposits-Companion/1.0.5"


class CommunityAPIError(BatchHTTPError):
    """Raised when the Community Deposits API cannot satisfy a request."""


def _response_json(response: requests.Response, *, context: str) -> dict[str, Any]:
    if response.status_code == 429:
        raise CommunityAPIError("Community Deposits HTTP 429: wait at least 60 seconds before trying again.", status=429)
    if response.status_code == 413:
        raise CommunityAPIError("Community Deposits HTTP 413: reduce the payload size before trying again.", status=413)
    if response.status_code != 200:
        raise CommunityAPIError(
            f"Community Deposits API returned HTTP {response.status_code} "
            f"for {context}.", status=response.status_code
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


def commander_identity(value):
    """Match the direct-report identity normalization used by the Worker."""
    return unicodedata.normalize("NFC", str(value or "").strip()).lower()


class SystemDeposits(list):
    """Catalog plus authenticated capability, including an empty result."""
    def __init__(self, records, can_report_state=False):
        super().__init__(records)
        self.can_report_state = can_report_state


def fetch_system_deposits(system: str, *, commander: str) -> list[dict[str, Any]]:
    system = str(system or "").strip()
    if not system:
        return []

    api_key = get_api_key(commander)
    if not api_key:
        raise CommunityAPIError(
            "Configure a Community Deposits API key in the plugin settings."
        )
    from .pagination import collect_pages
    capabilities = []
    def get_page(query):
        try:
            response = requests.get(DEPOSITS_URL, params=query,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Authorization": f"Bearer {api_key}"},
                timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            raise CommunityAPIError("Community Deposits request failed due to a network error.") from None
        payload = _response_json(response, context=system)
        deposits = payload.get("deposits") or []
        if not isinstance(deposits, list):
            raise CommunityAPIError("Community Deposits returned invalid deposits data.")
        permissions = payload.get("permissions")
        records = [dict(item) for item in deposits if isinstance(item, dict)]
        allowed = False
        if isinstance(permissions, dict):
            allowed = (permissions.get("can_write") is True and
                       commander_identity(permissions.get("commander")) == commander_identity(commander))
            for item in records:
                item["_can_report_state"] = allowed
        capabilities.append(allowed)
        return records, payload.get("next_cursor")
    records = collect_pages(get_page, {"system": system}, CommunityAPIError)
    return SystemDeposits(records, bool(capabilities) and all(capabilities))


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
