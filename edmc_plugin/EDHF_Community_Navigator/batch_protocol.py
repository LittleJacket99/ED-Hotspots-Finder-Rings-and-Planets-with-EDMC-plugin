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
