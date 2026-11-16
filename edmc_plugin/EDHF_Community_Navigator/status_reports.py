"""Direct status reports; independent from RhinoSpotter serialization and cache."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from .api_credentials import get_api_key
from .community_api import API_BASE, USER_AGENT, commander_identity

PENDING_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "HotspotsFinder" / "status_report_pending"


class StatusReportError(RuntimeError):
    def __init__(self, message, *, uncertain=False, retry_after=0, status=None):
        super().__init__(message)
        self.uncertain, self.retry_after, self.status = uncertain, retry_after, status


def pending_report_message(status=None, detail=None):
    """GUI guidance only; does not alter the pending operation or retry policy."""
    if status in (401, 403):
        return ("Status Report not confirmed. Correct the API Key/Write permissions before using "
                "Status Report → Retry pending Status Report.")
    message = "Status Report not confirmed. Use Status Report → Retry pending Status Report."
    # Keep server-directed waiting and definite rejection details visible.
    if status is not None and detail:
        message += " " + detail
    return message


def pending_path(commander):
    name = hashlib.sha256(commander_identity(commander).encode("utf-8")).hexdigest()
    return PENDING_DIR / (name + ".json")


def load_pending(commander):
    try:
        item = json.loads(pending_path(commander).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise StatusReportError("Cannot read the pending status report; no new report was sent.") from None
    try:
        valid = (isinstance(item, dict) and commander_identity(item["commander"]) == commander_identity(commander)
                 and type(item["deposit_id"]) is int and 0 < item["deposit_id"] <= 9007199254740991
                 and item["state"] in ("active", "depleted")
                 and str(uuid.UUID(item["operation_id"])) == item["operation_id"]
                 and isinstance(item.get("retry_at", 0), (int, float))
                 and math.isfinite(item.get("retry_at", 0))
                 and type(item.get("attempted", True)) is bool)
    except (KeyError, ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise StatusReportError("Invalid pending status report; no new report was sent.")
    return item


def prepare_operation(commander, deposit_id, state):
    if not commander.strip() or type(deposit_id) is not int or not 0 < deposit_id <= 9007199254740991 or state not in ("active", "depleted"):
        raise StatusReportError("Invalid status report selection.")
    item = dict(commander=commander.strip(), deposit_id=deposit_id, state=state, operation_id=str(uuid.uuid4()), attempted=False)
    path = pending_path(commander)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation prevents two confirmed operations from replacing
        # each other's retry identity. Persist before any request is made.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(item, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise StatusReportError("A status report is already pending. Retry that operation first.") from None
    return item


def _persist_pending(operation):
    path = pending_path(operation["commander"])
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(operation, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except OSError:
        raise StatusReportError("Cannot save pending report state. No further request will be sent.") from None


def _retry_seconds(value):
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            return max(0, math.ceil(seconds))
    except (ValueError, TypeError):
        pass
    try:
        return max(0, math.ceil(parsedate_to_datetime(value).timestamp() - time.time()))
    except (ValueError, TypeError, OverflowError):
        return 60


def _validate_receipt(payload, operation):
    try:
        event = payload["event"]
        stamp = datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00"))
        return (payload["status"] == "ok" and payload["action"] in ("created", "unchanged")
                and type(event["id"]) is int and event["id"] > 0
                and type(event["deposit_id"]) is int and event["deposit_id"] == operation["deposit_id"] and event["state"] == operation["state"]
                and commander_identity(event["commander"]) == commander_identity(operation["commander"])
                and stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def submit_pending(commander):
    operation = load_pending(commander)
    if operation is None:
        raise StatusReportError("No pending status report.")
    wait = math.ceil(operation.get("retry_at", 0) - time.time())
    if wait > 0:
        raise StatusReportError(f"Wait {wait} seconds before retrying.", retry_after=wait)
    key = get_api_key(commander)
    if not key:
        raise StatusReportError("Configure a usable Community Deposits API key; the report remains pending.")
    was_attempted = operation.get("attempted", True)
    # Persist before sending: a crash or lost response must remain ambiguous
    # even if a later retry is rejected after key revocation/permission changes.
    operation["attempted"] = True
    _persist_pending(operation)
    try:
        response = requests.post(f"{API_BASE}/v1/deposits/{operation['deposit_id']}/state-events",
            json={k: operation[k] for k in ("operation_id", "state")},
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=20, allow_redirects=False)
    except requests.RequestException:
        raise StatusReportError("Status report outcome not confirmed. Retry the pending operation manually.", uncertain=True) from None
    if response.status_code == 429:
        wait = _retry_seconds(response.headers.get("Retry-After", "60"))
        operation["retry_at"] = time.time() + wait
        operation["attempted"] = was_attempted
        _persist_pending(operation)
        raise StatusReportError(f"HTTP 429: wait {wait} seconds, then retry manually.", retry_after=wait, status=429)
    if response.status_code in (400, 401, 403, 404, 409, 413, 415):
        if not was_attempted:
            pending_path(commander).unlink()
        messages = {400: "Invalid status report.", 401: "API key invalid or revoked.", 403: "Write permission or Commander association required.",
                    404: "Deposit no longer available.", 409: "Operation ID conflicts with an existing report.", 413: "Status report payload too large.", 415: "Unsupported request format."}
        suffix = " The original operation remains pending because an earlier outcome was not confirmed." if was_attempted else ""
        raise StatusReportError(f"HTTP {response.status_code}: {messages[response.status_code]}{suffix}", status=response.status_code)
    if response.status_code not in (200, 201):
        raise StatusReportError("Status report outcome not confirmed. Retry the pending operation manually.", uncertain=True)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not _validate_receipt(payload, operation):
        raise StatusReportError("Invalid receipt; status report outcome not confirmed. Retry manually.", uncertain=True)
    try:
        pending_path(commander).unlink()
    except OSError:
        raise StatusReportError("Report recorded, but local receipt cleanup failed. Retry the same pending operation.", uncertain=True) from None
    receipt = dict(payload["event"])
    shared = payload.get("shared_state")
    if isinstance(shared, dict) and shared.get("state") in ("active", "depleted"):
        receipt["shared_state"] = shared
    return receipt


def direct_report_text(event, now=None):
    if not isinstance(event, dict) or event.get("state") not in ("active", "depleted"):
        return "Direct report: none", "", ""
    try:
        original = event["recorded_at"]
        stamp = datetime.fromisoformat(original.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError()
        seconds = max(0, int(((now or datetime.now(timezone.utc)) - stamp).total_seconds()))
        days, hours, minutes = seconds // 86400, seconds // 3600, seconds // 60
        count, unit = (days, "day") if days else ((hours, "hour") if hours else (minutes, "minute"))
        age = f"{count} {unit}{'' if count == 1 else 's'} ago" if count else "just now"
        return f"Direct report: {event['state'].title()} — {age}", f"Reported by {event.get('commander', '')}", f"Recorded at {original} (UTC)"
    except (KeyError, ValueError, TypeError, AttributeError):
        return "Direct report: unavailable", "", ""
