#!/usr/bin/env python3

"""GUI-friendly wrapper around the RhinoSpotter synchronization logic."""

import sqlite3
from edmc_plugin.EDHF_Community_Navigator.community_api import BATCH_PAUSE_SECONDS
from contextlib import closing
from pathlib import Path
from time import sleep
from collections import defaultdict

from edmc_plugin.EDHF_Community_Navigator.api_credentials import (
    credential_configured,
    get_api_key,
)
from edmc_plugin.EDHF_Community_Navigator.batch_protocol import (
    validate_batch_request,
    validate_batch_response,
    record_sync_failure, initialize_outcomes, cache_outcomes, transport_failure,
)
from edmc_plugin.EDHF_Community_Navigator.sync_state_lock import sync_state_mutex
from edmc_plugin.EDHF_Community_Navigator.sync_plan import (
    apply_credential_availability,
    build_sync_plan,
    record_fingerprint,
    record_state_key,
)
from rhinospotter_sync import (
    MAX_BATCH_SIZE,
    chunks,
    get_sync_state_entry,
    load_rhinospotter_records,
    record_fingerprint,
    record_state_key,
    resolve_source,
    save_sync_state_entry,
    send_batch,
)


class RhinoSpotterSyncError(RuntimeError):
    pass


def inspect_source(data_path=None):
    """Return the detected RhinoSpotter source and a lightweight summary."""

    source_type, source_path = resolve_source(data_path)

    if source_type == "rs_api":
        loaded = load_rhinospotter_records(data_path)
        return {
            "source_type": source_type,
            "source_path": str(source_path),
            "records_found": int(loaded["records_found"] or 0),
            "records_valid": int(loaded["records_valid"] or 0),
            "radius_inferred": int(loaded["radius_inferred"] or 0),
            "radius_missing": int(loaded["radius_missing"] or 0),
            "api_version": loaded.get("api_version", ""),
            "api_schema": loaded.get("api_schema"),
            "revision": loaded.get("revision"),
        }

    if source_type == "sqlite":
        try:
            uri = Path(source_path).resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=5.0)
            with closing(connection) as conn:
                records_found = conn.execute(
                    "SELECT COUNT(*) FROM bookmarks"
                ).fetchone()[0]
        except sqlite3.Error as exc:
            raise RhinoSpotterSyncError(
                f"Could not inspect RhinoSpotter database {source_path}: {exc}"
            ) from exc
    else:
        records_found = sum(1 for _ in Path(source_path).rglob("*.json"))

    return {
        "source_type": source_type,
        "source_path": str(source_path),
        "records_found": int(records_found or 0),
    }


def sync_bookmarks(data_path=None):
    """Reject legacy direct uploads; a preview and explicit confirmation are required."""
    del data_path
    raise RhinoSpotterSyncError(
        "Direct bookmark sync is disabled. Use preview_sync() and confirm_sync()."
    )


def _read_sync_inputs(data_path=None, *, check_credentials=False):
    source_type, source_path = resolve_source(data_path)
    # Pin this read to the resolved source so Settings changes or discovery
    # races cannot pair records from one source with another source's cache key.
    loaded = load_rhinospotter_records(source_path)
    state = get_sync_state_entry(source_type, source_path)
    previous = state.get("fingerprints", {})
    if not isinstance(previous, dict):
        previous = {}
    plan = build_sync_plan(
        records=loaded["deposits"], previous_fingerprints=previous,
        loaded=loaded, source_type=source_type, source_path=str(source_path),
        state_entry=state,
    )
    if check_credentials:
        plan = apply_credential_availability(plan, credential_configured)
    return source_type, source_path, loaded, state, plan


def preview_sync(data_path=None):
    """Read and classify bookmarks without sending or persisting state."""
    with sync_state_mutex():
        return _read_sync_inputs(data_path, check_credentials=True)[-1]


def confirm_sync(data_path, expected_snapshot):
    """Revalidate a preview under the shared mutex, then run its exact plan."""
    with sync_state_mutex():
        source_type, source_path, loaded, state, plan = _read_sync_inputs(
            data_path, check_credentials=True
        )
        if plan["snapshot"] != expected_snapshot:
            return {"stale": True, "plan": plan}
        return _execute_sync_plan(source_type, source_path, loaded, state, plan)


def _execute_sync_plan(source_type, source_path, loaded, state, plan):
    deposits = loaded["deposits"]
    current_fingerprints = plan["current_fingerprints"]
    records_to_send = [item["record"] for item in plan["pending"]]
    removed_local = plan["removed_local"]

    summary = {
        "source_type": loaded["source_type"],
        "source_path": str(loaded["source_path"]),
        "records_found": loaded["records_found"],
        "records_valid": loaded["records_valid"],
        "read_errors": loaded["read_errors"],
        "radius_inferred": loaded.get("radius_inferred", 0),
        "radius_missing": loaded.get("radius_missing", 0),
        "api_version": loaded.get("api_version", ""),
        "api_schema": loaded.get("api_schema"),
        "revision": loaded.get("revision"),
        "revision_unchanged": bool(
            state.get("complete")
            and state.get("revision") == loaded.get("revision")
        ),
        "records_sent": len(records_to_send),
        "local_unchanged": plan["unchanged"],
        "removed_local": removed_local,
        "inserted": 0,
        "matched": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": loaded["read_errors"] + plan["commander_mismatches"],
        "state_saved": False,
    }

    initialize_outcomes(summary, plan)
    successful_keys = set()
    sent_count = 0
    by_commander = defaultdict(list)
    for record in records_to_send:
        commander = str(record.get("commander") or "").strip()
        if commander:
            by_commander[commander.lower()].append((commander, record))
        else:
            summary["errors"] += 1

    for commander_items in by_commander.values():
        commander = commander_items[0][0]
        api_key = get_api_key(commander)
        if not api_key:
            for _, record in commander_items:
                record_sync_failure(summary, str(record["report_id"]), {"error_code":"AUTH_REQUIRED"}, record)
            continue
        throttled = False
        attempted_batch = False
        for batch_items in chunks([record for _, record in commander_items], MAX_BATCH_SIZE):
            try:
                validate_batch_request(batch_items)
            except ValueError as exc:
                raise RhinoSpotterSyncError(str(exc)) from exc
            metadata_by_report = {
                str(record["report_id"]): (
                    record_state_key(record), record_fingerprint(record)
                )
                for record in batch_items
            }
            # The key profile is checked locally before sending; the Worker
            # enforces the same commander association as the final authority.
            if any(
                str(record.get("commander") or "").strip().lower()
                != commander.lower()
                for record in batch_items
            ):
                raise RhinoSpotterSyncError(
                    "Bookmark commander does not match the configured API profile."
                )
            if throttled:
                for record in batch_items:
                    record_sync_failure(summary, str(record["report_id"]), {}, record)
                continue
            if attempted_batch:
                sleep(BATCH_PAUSE_SECONDS)
            attempted_batch = True
            sent_count += len(batch_items)
            try:
                result = send_batch(batch_items, api_key=api_key)
            except (RuntimeError, OSError, ValueError) as exc:
                # Only confirmed receipts advance fingerprints. Later independent
                # batches still run; throttling stops further HTTP until manual Sync.
                throttled = "429" in str(exc)
                if throttled:
                    summary["throttled"] = True
                for record in batch_items:
                    record_sync_failure(summary, str(record["report_id"]), transport_failure(exc), record)
                continue
            try:
                result_by_report = validate_batch_response(batch_items, result)
            except ValueError:
                # An untrusted/incomplete receipt never advances fingerprints.
                for record in batch_items:
                    record_sync_failure(summary, str(record["report_id"]), {}, record)
                continue
            for report_id, item in result_by_report.items():
                if not item["ok"]:
                    record_sync_failure(summary, report_id, item, next(record for record in batch_items if str(record["report_id"]) == report_id))
                    continue
                summary["synced"] += 1
                action = item["action"]
                if action == "inserted":
                    summary["inserted"] += 1
                elif action == "matched_existing_deposit":
                    summary["matched"] += 1
                elif action == "updated_report":
                    summary["updated"] += 1
                else:
                    summary["unchanged"] += 1
                successful_keys.add(metadata_by_report[report_id][0])

    summary["records_sent"] = sent_count

    # Complete means this stable revision was handled, including known skips;
    # it never counts a rejection as synced. Recoverable failures stay pending.
    # Accepted fingerprints and rejected versions remain separate below.
    complete = not summary["pending_reports"] and not loaded["read_errors"] and not plan["commander_mismatches"]
    if source_type == "rs_api" and not loaded.get("revision_stable"):
        complete = False

    try:
        with sync_state_mutex():
            latest = get_sync_state_entry(source_type, source_path)
            saved_fingerprints, saved_depletion_states, saved_rejections = cache_outcomes(latest, plan, successful_keys, summary)
            state_entry = {
                "complete": complete,
                "revision": (
                    loaded.get("revision")
                    if complete and source_type == "rs_api" else None
                ),
                "records_found": loaded["records_found"],
                "records_valid": loaded["records_valid"],
                "radius_inferred": loaded.get("radius_inferred", 0),
                "radius_missing": loaded.get("radius_missing", 0),
                "fingerprints": saved_fingerprints,
                "depletion_states": saved_depletion_states,
                "rejections": saved_rejections,
            }
            save_sync_state_entry(source_type, source_path, state_entry)
    except OSError as exc:
        summary["state_error"] = str(exc)
    else:
        summary["state_saved"] = True

    return summary


def sync_cards(cards_dir=None):
    """Backward-compatible name used by older GUI layers.

    Automatic discovery now prefers RhinoSpotter rs_api. Older SQLite and JSON
    sources remain available as compatibility fallbacks.
    """

    return sync_bookmarks(data_path=cards_dir)
