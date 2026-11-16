"""Strict validation for Community Deposits batch responses."""

from __future__ import annotations


SUCCESS_ACTIONS = frozenset({
    "inserted",
    "matched_existing_deposit",
    "updated_report",
    "unchanged",
})


class BatchProtocolError(ValueError):
    pass


class BatchHTTPError(RuntimeError):
    def __init__(self, message, *, status=None, retry_after=0):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


TERMINAL_CODES = frozenset({"STALE_UPDATE", "ACTIVE_TRANSITION_UNVERIFIABLE", "INVALID_REPORT"})


def initialize_outcomes(summary, plan):
    summary.update(synced=plan.get("unchanged", 0), skipped=plan.get("skipped", 0),
                   skipped_reports=list(plan.get("skipped_reports", [])), pending_reports=[], _rejections={},
                   local_invalid=plan.get("invalid",0), commander_mismatches=plan.get("commander_mismatches",0))


def transport_failure(exc):
    # Only a confirmed rejection of the entire request is terminal. Ambiguous
    # responses/transport errors always remain pending. Auth is never data-skip.
    status = getattr(exc, "status", None)
    if status in (401, 403): return {"error_code": "AUTH_REQUIRED"}
    if status in (400, 413, 415): return {"error_code": "INVALID_REPORT"}
    return {}


def record_sync_failure(summary, report_id, item, record=None):
    from .sync_plan import record_state_key, rejection_fingerprint
    summary["errors"] += 1
    code = item.get("error_code") or "OTHER"
    counts = summary.setdefault("failure_codes", {})
    counts[code] = counts.get(code, 0) + 1
    if code in TERMINAL_CODES:
        summary["skipped"] = summary.get("skipped", 0) + 1
        summary.setdefault("skipped_reports", []).append({"report_id": report_id, "error_code": code})
        if record is not None:
            summary.setdefault("_rejections", {})[record_state_key(record)] = {"fingerprint": rejection_fingerprint(record), "reason": code}
    else:
        recovery = "credentials" if code == "AUTH_REQUIRED" else "retry"
        summary.setdefault("pending_reports", []).append({"report_id": report_id, "error_code": code, "recovery": recovery})


def cache_outcomes(latest, plan, successful_keys, summary):
    # Never store a rejected version in the accepted-fingerprint namespace.
    def mapping(name):
        value = latest.get(name, {})
        return dict(value) if isinstance(value, dict) else {}
    accepted = mapping("fingerprints")
    depletion = mapping("depletion_states")
    rejections = mapping("rejections")
    for key in set(successful_keys) | set(plan.get("accepted_unchanged_keys", [])):
        accepted[key] = plan["current_fingerprints"][key]
        if key in plan["current_depletion_states"]:
            depletion[key] = plan["current_depletion_states"][key]
        rejections.pop(key, None)
    rejections.update(summary.pop("_rejections", {}))
    current = plan["current_fingerprints"]
    if not plan.get("invalid") and not plan.get("commander_mismatches"):
        accepted = {k:v for k,v in accepted.items() if k in current}
        depletion = {k:v for k,v in depletion.items() if k in current}
        rejections = {k:v for k,v in rejections.items() if k in current}
    return accepted, depletion, rejections


def outcome_summary(summary):
    synced = summary.get("synced", sum(summary.get(k, 0) for k in ("inserted", "matched", "updated", "unchanged", "local_unchanged")))
    pending = len(summary.get("pending_reports", [])) if "pending_reports" in summary else summary.get("errors", 0)
    return f"{synced} Synced · {summary.get('skipped', 0)} Skipped · {pending} Pending"


def sync_failure_text(summary, *, retry_command="Sync Bookmarks"):
    counts = {}
    for item in summary.get("skipped_reports", []):
        code = item.get("error_code")
        counts[code] = counts.get(code, 0) + 1
    parts = []
    if counts.get("ACTIVE_TRANSITION_UNVERIFIABLE"):
        parts.append(f"Unverified Active: {counts['ACTIVE_TRANSITION_UNVERIFIABLE']} skipped. Use Status Report → Report Active after checking the deposit.")
    if counts.get("STALE_UPDATE"):
        parts.append(f"Outdated source version: {counts['STALE_UPDATE']} skipped; edit or re-mark in RhinoSpotter to supply a valid newer version.")
    if counts.get("INVALID_REPORT"):
        parts.append(f"Invalid data: {counts['INVALID_REPORT']} skipped; correct the source data.")
    if summary.get("local_invalid"):
        parts.append(f"Invalid source records: {summary['local_invalid']} skipped; correct the bookmark data.")
    if summary.get("commander_mismatches"):
        parts.append(f"Commander/profile mismatch: {summary['commander_mismatches']} skipped; select the matching profile.")
    pending = summary.get("pending_reports", [])
    credentials_pending = sum(item.get("recovery") == "credentials" for item in pending)
    retry_pending = sum(item.get("recovery", "retry") == "retry" for item in pending)
    if credentials_pending:
        parts.append(f"{credentials_pending} Pending — correct the API Key/Write permissions before using {retry_command} to retry.")
    if retry_pending:
        parts.append(f"{retry_pending} Pending — use {retry_command} to retry")
    if summary.get("throttled") and pending:
        parts.append("API rate limit reached; wait at least 60 seconds before retrying.")
    if summary.get("state_error"):
        parts.append("Local synchronization cache was not saved; server receipts and local cache differ.")
    return " ".join(parts)


def validate_batch_request(sent_records):
    """Reject batches that cannot be mapped back to one unique source record."""
    if not isinstance(sent_records, (list, tuple)):
        raise BatchProtocolError("Batch request must be a list of records.")
    sent_ids = []
    for record in sent_records:
        if not isinstance(record, dict):
            raise BatchProtocolError("Batch contains an invalid record.")
        report_id = record.get("report_id")
        if (
            not isinstance(report_id, str)
            or not report_id.strip()
            or report_id != report_id.strip()
        ):
            raise BatchProtocolError("Batch contains a missing or invalid report_id.")
        sent_ids.append(report_id)
    if len(set(sent_ids)) != len(sent_ids):
        raise BatchProtocolError("Batch contains duplicate report_id values.")
    return sent_ids


def validate_batch_response(sent_records, payload):
    """Return response entries keyed by sent report id, rejecting ambiguity."""
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise BatchProtocolError("Community Deposits returned an invalid batch status.")
    sent_ids = validate_batch_request(sent_records)
    received = payload.get("received")
    if type(received) is not int or received != len(sent_records):
        raise BatchProtocolError("Community Deposits returned an inconsistent received count.")
    items = payload.get("results")
    if not isinstance(items, list) or len(items) != len(sent_records):
        raise BatchProtocolError("Community Deposits returned an incomplete batch result list.")
    expected = set(sent_ids)
    mapped = {}
    for item in items:
        if not isinstance(item, dict):
            raise BatchProtocolError("Community Deposits returned an invalid batch result.")
        report_id = item.get("report_id")
        if not isinstance(report_id, str) or report_id not in expected:
            raise BatchProtocolError("Community Deposits returned a missing or unexpected report_id.")
        if report_id in mapped:
            raise BatchProtocolError("Community Deposits returned a duplicate report_id.")
        if not isinstance(item.get("ok"), bool):
            raise BatchProtocolError("Community Deposits returned a non-boolean result status.")
        if item["ok"] and item.get("action") not in SUCCESS_ACTIONS:
            raise BatchProtocolError("Community Deposits returned an unknown success action.")
        mapped[report_id] = item
    if set(mapped) != expected:
        raise BatchProtocolError("Community Deposits omitted a batch report_id.")
    return mapped
