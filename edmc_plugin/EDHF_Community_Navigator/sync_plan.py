"""Pure RhinoSpotter sync planning shared by Finder and the EDMC plugin."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
from typing import Any


class _NoBytecodeSourceLoader(importlib.machinery.SourceFileLoader):
    """Load the external RhinoSpotter API without creating a local .pyc."""

    def set_data(self, path, data, *args, **kwargs):
        return None


def load_source_module(name: str, path: str | Path):
    loader = _NoBytecodeSourceLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    if spec is None:
        raise ImportError(f"Could not load Python module: {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def record_state_key(record: dict[str, Any]) -> str:
    source_record_id = record.get("source_record_id")
    if source_record_id not in (None, ""):
        return f"id:{source_record_id}"
    return f"report:{record.get('report_id', '')}"


def _record_fingerprint(record: dict[str, Any], *, include_version: bool) -> str:
    # Null and omitted active-state snapshots remain equivalent here; explicit
    # reactivation is handled separately from fingerprinting by build_sync_plan.
    record = {key: value for key, value in record.items()
              if not (key == "depleted_at" and value is None)
              and (include_version or key != "updated_at")}
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_fingerprint(record: dict[str, Any]) -> str:
    # Versions alone are not observations/content. Technical metadata stays in
    # this sync fingerprint so a real missing-radius/ID completion is sent once.
    return _record_fingerprint(record, include_version=False)


def rejection_fingerprint(record):
    # A real source version can resolve a rejection even when content is equal.
    # Normal successful fingerprints deliberately continue to ignore versions.
    return _record_fingerprint(record, include_version=True)


def _digest(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_sync_plan(
    *,
    records: list[dict[str, Any]],
    previous_fingerprints: dict[str, str],
    loaded: dict[str, Any],
    source_type: str,
    source_path: str,
    state_entry: dict[str, Any],
    commander: str | None = None,
) -> dict[str, Any]:
    """Classify normalized records without network or filesystem writes."""
    expected = (commander or "").strip().casefold()
    current: dict[str, str] = {}
    current_depletion_states: dict[str, str | None] = {}
    pending: list[dict[str, Any]] = []
    previous_depletion_states = state_entry.get("depletion_states", {})
    if not isinstance(previous_depletion_states, dict):
        previous_depletion_states = {}
    unchanged = 0
    accepted_unchanged_keys = []
    rejected = state_entry.get("rejections", {})
    if not isinstance(rejected, dict):
        rejected = {}
    skipped_reports = []
    mismatches = 0
    for record in records:
        actual = str(record.get("commander") or "").strip()
        if not actual or (expected and actual.casefold() != expected):
            mismatches += 1
            continue
        key = record_state_key(record)
        fingerprint = record_fingerprint(record)
        current[key] = fingerprint
        if "depleted_at" in record:
            current_depletion_states[key] = record.get("depleted_at")
        old = previous_fingerprints.get(key)
        upload_record = dict(record)
        depletion = record.get("depleted_at", _MISSING)
        previous_depletion = previous_depletion_states.get(key, _MISSING)
        if depletion is None and previous_depletion in (_MISSING, None):
            upload_record.pop("depleted_at", None)
        elif depletion is _MISSING:
            upload_record.pop("depleted_at", None)
        refusal = rejected.get(key)
        if isinstance(refusal, dict) and refusal.get("fingerprint") == rejection_fingerprint(upload_record):
            skipped_reports.append({"report_id": record.get("report_id"), "error_code": refusal.get("reason", "INVALID_REPORT")})
        elif old == fingerprint or old == _record_fingerprint(record, include_version=True):
            unchanged += 1
            accepted_unchanged_keys.append(key)
            status = "Unchanged"
        else:
            status = "New" if old is None else "Modified"
            pending.append({"record": upload_record, "status": status})

    invalid = max(
        0,
        int(loaded.get("records_found", 0) or 0)
        - int(loaded.get("records_valid", len(records)) or 0),
    )
    effective_commander = commander or " / ".join(sorted({
        str(r.get("commander") or "").strip() for r in records
        if str(r.get("commander") or "").strip()
    }, key=str.casefold))
    source_snapshot = {
        "source_type": source_type,
        "source_path": source_path,
        "records": [(record_state_key(r), rejection_fingerprint(r)) for r in records],
        "records_found": loaded.get("records_found"),
        "records_valid": loaded.get("records_valid"),
        "revision_before": loaded.get("revision_before"),
        "revision": loaded.get("revision"),
        "revision_stable": loaded.get("revision_stable"),
        "read_errors": loaded.get("read_errors"),
        "api_version": loaded.get("api_version"),
        "api_schema": loaded.get("api_schema"),
        "radius_inferred": loaded.get("radius_inferred"),
        "radius_missing": loaded.get("radius_missing"),
        "invalid": invalid,
        "commander_mismatches": mismatches,
        "commander": effective_commander,
    }
    return {
        "source_type": source_type,
        "source_path": source_path,
        "commander": effective_commander,
        "records_found": int(loaded.get("records_found", 0) or 0),
        "records_valid": int(loaded.get("records_valid", len(records)) or 0),
        "invalid": invalid,
        "commander_mismatches": mismatches,
        "skipped": invalid + mismatches + len(skipped_reports),
        "skipped_reports": skipped_reports,
        "new": sum(item["status"] == "New" for item in pending),
        "modified": sum(item["status"] == "Modified" for item in pending),
        "unchanged": unchanged,
        "accepted_unchanged_keys": accepted_unchanged_keys,
        "pending": pending,
        "current_fingerprints": current,
        "current_depletion_states": current_depletion_states,
        "removed_local": len(set(previous_fingerprints) - set(current)),
        "snapshot": _digest({
            "cache": state_entry,
            "source": source_snapshot,
            "commander": effective_commander,
        }),
    }


_MISSING = object()


def apply_credential_availability(
    plan: dict[str, Any], is_configured,
) -> dict[str, Any]:
    """Filter the preview to records whose Commander credential is present.

    Only the boolean availability is retained; credential contents never enter
    the plan, snapshot, UI, or logs.
    """
    available: dict[str, bool] = {}
    preview_pending = []
    for item in plan["pending"]:
        record = item["record"]
        commander = str(record.get("commander") or "").strip()
        key = commander.casefold()
        if key not in available:
            available[key] = bool(is_configured(commander))
        if available[key]:
            preview_pending.append(item)
    missing = len(plan["pending"]) - len(preview_pending)
    plan["preview_pending"] = preview_pending
    plan["credential_missing"] = missing
    plan["new"] = sum(item["status"] == "New" for item in preview_pending)
    plan["modified"] = sum(item["status"] == "Modified" for item in preview_pending)
    plan["skipped"] = (
        plan["invalid"] + plan["commander_mismatches"] + len(plan.get("skipped_reports", []))
    )
    plan["snapshot"] = _digest({
        "plan": plan["snapshot"],
        "credential_availability": sorted(available.items()),
    })
    return plan
