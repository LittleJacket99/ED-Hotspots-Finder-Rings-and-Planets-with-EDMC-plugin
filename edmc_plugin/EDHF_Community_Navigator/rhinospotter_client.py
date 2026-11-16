from __future__ import annotations

import hashlib
import os
import json
import sys
from pathlib import Path
from time import sleep
from types import ModuleType
from typing import Any

from .api_credentials import credential_configured, get_api_key
from .batch_protocol import validate_batch_request, validate_batch_response, record_sync_failure, initialize_outcomes, cache_outcomes, transport_failure
from .sync_state_lock import sync_state_mutex
from .sync_plan import (
    apply_credential_availability,
    build_sync_plan,
    load_source_module,
    record_fingerprint,
    record_state_key,
)
from .community_api import chunks, send_deposit_batch, BATCH_PAUSE_SECONDS


SUPPORTED_SCHEMA = 1

APP_DATA_DIR = (
    Path(os.environ.get("APPDATA") or Path.home())
    / "HotspotsFinder"
)

SYNC_STATE_PATH = APP_DATA_DIR / "rhinospotter_sync_state.json"
SYNC_STATE_VERSION = 1


class RhinoSpotterError(RuntimeError):
    """Raised when RhinoSpotter cannot be read or synchronized."""


class RhinoSpotterNotInstalled(RhinoSpotterError):
    """Raised when a compatible RhinoSpotter EDMC plugin is unavailable."""


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _state_source_key(path: Path) -> str:
    normalised = os.path.normcase(
        os.path.abspath(str(path.expanduser()))
    )
    return f"rs_api:{normalised}"


def _load_sync_state() -> dict[str, Any]:
    try:
        with sync_state_mutex():
            state = json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": SYNC_STATE_VERSION,
            "sources": {},
        }

    if (
        not isinstance(state, dict)
        or state.get("version") != SYNC_STATE_VERSION
        or not isinstance(state.get("sources"), dict)
    ):
        return {
            "version": SYNC_STATE_VERSION,
            "sources": {},
        }

    return state


def _get_sync_state_entry(path: Path) -> dict[str, Any]:
    state = _load_sync_state()
    entry = state["sources"].get(_state_source_key(path), {})
    return dict(entry) if isinstance(entry, dict) else {}


def _save_sync_state_entry(path: Path, entry: dict[str, Any]) -> None:
    with sync_state_mutex():
        state = _load_sync_state_unlocked()
        state["sources"][_state_source_key(path)] = dict(entry)
        SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = SYNC_STATE_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(SYNC_STATE_PATH)


def _load_sync_state_unlocked() -> dict[str, Any]:
    try:
        state = json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": SYNC_STATE_VERSION, "sources": {}}
    if (not isinstance(state, dict) or state.get("version") != SYNC_STATE_VERSION
            or not isinstance(state.get("sources"), dict)):
        return {"version": SYNC_STATE_VERSION, "sources": {}}
    return state


def _record_state_key(record: dict[str, Any]) -> str:
    return record_state_key(record)


def _record_fingerprint(record: dict[str, Any]) -> str:
    return record_fingerprint(record)


def _api_revision(module: ModuleType) -> Any:
    try:
        return module.revision()
    except Exception:
        return None


def _api_version(module: ModuleType) -> str:
    try:
        return str(module.version())
    except Exception:
        return ""


def resolve_rs_api(plugin_dir: str | Path) -> Path:
    plugin_dir = Path(plugin_dir).resolve()
    path = plugin_dir.parent / "RhinoSpotter" / "rs_api.py"
    if not path.is_file():
        raise RhinoSpotterNotInstalled(
            "RhinoSpotter not found. Install or update RhinoSpotter 5.1+ "
            "as an EDMC plugin, then restart EDMC."
        )
    return path


def _load_rs_api(path: Path) -> ModuleType:
    plugin_path = str(path.parent)
    added_path = plugin_path not in sys.path
    if added_path:
        sys.path.insert(0, plugin_path)

    try:
        module = load_source_module("edhf_community_navigator_rs_api", path)
    except RhinoSpotterError:
        raise
    except Exception as exc:
        raise RhinoSpotterError(
            f"Could not import RhinoSpotter API {path}: {exc}"
        ) from exc
    finally:
        if added_path:
            try:
                sys.path.remove(plugin_path)
            except ValueError:
                pass

    schema = getattr(module, "SCHEMA", None)
    if schema != SUPPORTED_SCHEMA:
        raise RhinoSpotterError(
            f"Unsupported RhinoSpotter API schema {schema!r}; "
            f"expected schema {SUPPORTED_SCHEMA}."
        )

    return module


def _report_id(record: dict[str, Any]) -> str:
    identity = {
        "source": "rhinospotter",
        "source_record_id": record.get("source_record_id"),
        "commander": _clean_text(record.get("commander")),
        "system": _clean_text(record.get("system")),
        "planet_name": _clean_text(record.get("planet_name")),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "marked_at": _clean_text(record.get("marked_at")),
    }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"rhino-{digest}"


def _api_record(mark: dict[str, Any]) -> dict[str, Any]:
    record = {
        "source_record_id": mark.get("id"),
        "commander": mark.get("commander"),
        "system": mark.get("system"),
        "planet_name": mark.get("body"),
        "location_index": mark.get("location"),
        "latitude": mark.get("latitude"),
        "longitude": mark.get("longitude"),
        "planet_radius": mark.get("planet_radius"),
        "commodity": mark.get("material"),
        "rigs": mark.get("rigs"),
        "amount": mark.get("amount"),
        "density": mark.get("density"),
        "heading": mark.get("heading"),
        "marked_at": mark.get("marked_at"),
        "updated_at": mark.get("updated_at"),
        "system_address": mark.get("system_address"),
        "body_id": mark.get("body_id"),
    }
    if "depleted_at" in mark:
        record["depleted_at"] = mark["depleted_at"]
    return record


def _body_key(record: dict[str, Any]) -> tuple[str, str] | None:
    system = _clean_text(record.get("system"))
    body = _clean_text(record.get("planet_name"))
    if not system or not body:
        return None
    return system.casefold(), body.casefold()


def _propagate_planet_radii(records: list[dict[str, Any]]) -> tuple[int, int]:
    known: dict[tuple[str, str], Any] = {}
    for record in records:
        key = _body_key(record)
        radius = record.get("planet_radius")
        if key is not None and radius not in (None, ""):
            known.setdefault(key, radius)

    inferred = 0
    missing = 0
    for record in records:
        if record.get("planet_radius") not in (None, ""):
            continue
        key = _body_key(record)
        radius = known.get(key) if key is not None else None
        if radius is None:
            missing += 1
        else:
            record["planet_radius"] = radius
            inferred += 1

    return inferred, missing


def _normalise_record(record: dict[str, Any]) -> dict[str, Any]:
    required = ("system", "planet_name", "latitude", "longitude", "commodity")
    missing = [
        key for key in required
        if record.get(key) is None or record.get(key) == ""
    ]
    if missing:
        raise RhinoSpotterError(
            "RhinoSpotter bookmark is missing required fields: "
            + ", ".join(missing)
        )

    payload = {
        "report_id": _report_id(record),
        "source": "rhinospotter",
        "source_record_id": record.get("source_record_id"),
        "commander": _clean_text(record.get("commander")),
        "system": _clean_text(record.get("system")),
        "planet_name": _clean_text(record.get("planet_name")),
        "location_index": record.get("location_index"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "planet_radius": record.get("planet_radius"),
        "commodity": _clean_text(record.get("commodity")),
        "rigs": record.get("rigs"),
        "amount": _clean_text(record.get("amount")),
        "density": _clean_text(record.get("density")),
        "heading": record.get("heading"),
        "marked_at": _clean_text(record.get("marked_at")),
        "updated_at": _clean_text(record.get("updated_at")),
        "system_address": record.get("system_address"),
        "body_id": record.get("body_id"),
    }

    if "depleted_at" in record:
        payload["depleted_at"] = _clean_text(record.get("depleted_at"))

    return {
        key: value for key, value in payload.items()
        if value is not None or key == "depleted_at" and key in payload
    }


def load_bookmarks(
    plugin_dir: str | Path,
    *,
    path: Path | None = None,
    module: ModuleType | None = None,
    revision_before: Any = None,
) -> dict[str, Any]:
    path = path or resolve_rs_api(plugin_dir)
    module = module or _load_rs_api(path)

    if revision_before is None:
        revision_before = _api_revision(module)

    try:
        bookmarks = module.bookmarks()
    except Exception as exc:
        raise RhinoSpotterError(
            f"RhinoSpotter API could not read bookmarks: {exc}"
        ) from exc

    if not isinstance(bookmarks, list):
        raise RhinoSpotterError(
            "RhinoSpotter API returned an unexpected bookmarks value."
        )

    raw_records = [
        _api_record(mark)
        for mark in bookmarks
        if isinstance(mark, dict)
    ]
    inferred, missing_radius = _propagate_planet_radii(raw_records)

    records: list[dict[str, Any]] = []
    errors = 0
    for record in raw_records:
        try:
            records.append(_normalise_record(record))
        except RhinoSpotterError:
            errors += 1

    revision_after = _api_revision(module)

    return {
        "records_found": len(bookmarks),
        "records_valid": len(records),
        "read_errors": errors,
        "radius_inferred": inferred,
        "radius_missing": missing_radius,
        "api_version": _api_version(module),
        "api_schema": getattr(module, "SCHEMA", None),
        "revision_before": revision_before,
        "revision": revision_after,
        "revision_stable": (
            revision_before is not None
            and revision_after is not None
            and revision_before == revision_after
        ),
        "records": records,
    }


def sync_bookmarks(
    plugin_dir: str | Path, *, commander: str | None = None
) -> dict[str, Any]:
    """Reject legacy direct uploads; a preview and explicit confirmation are required."""
    del plugin_dir, commander
    raise RhinoSpotterError(
        "Direct bookmark sync is disabled. Use preview_sync() and confirm_sync()."
    )


def _read_sync_inputs(
    plugin_dir: str | Path, commander: str, *, check_credentials: bool = False
):
    path = resolve_rs_api(plugin_dir)
    module = _load_rs_api(path)
    revision_before = _api_revision(module)
    loaded = load_bookmarks(
        plugin_dir, path=path, module=module, revision_before=revision_before
    )
    state = _get_sync_state_entry(path)
    previous = state.get("fingerprints", {})
    if not isinstance(previous, dict):
        previous = {}
    plan = build_sync_plan(
        records=loaded["records"], previous_fingerprints=previous,
        loaded=loaded, source_type="rs_api", source_path=str(path),
        state_entry=state, commander=commander,
    )
    if check_credentials:
        plan = apply_credential_availability(plan, credential_configured)
    # Preserve the plugin's existing all-or-nothing active-Commander check.
    plan["confirm_blocked"] = bool(plan["commander_mismatches"])
    return path, loaded, state, plan


def preview_sync(plugin_dir: str | Path, *, commander: str) -> dict[str, Any]:
    """Build a read-only preview under the shared sync mutex."""
    if not (commander or "").strip():
        raise RhinoSpotterError("Active commander is required to preview bookmarks.")
    with sync_state_mutex():
        return _read_sync_inputs(
            plugin_dir, commander, check_credentials=True
        )[-1]


def confirm_sync(
    plugin_dir: str | Path, *, commander: str, expected_snapshot: str
) -> dict[str, Any]:
    """Rebuild and validate the preview before invoking the existing uploader."""
    if not (commander or "").strip():
        raise RhinoSpotterError("Active commander is required to synchronize bookmarks.")
    with sync_state_mutex():
        path, loaded, state, plan = _read_sync_inputs(
            plugin_dir, commander, check_credentials=True
        )
        if plan["snapshot"] != expected_snapshot:
            return {"stale": True, "plan": plan}
        if plan["commander_mismatches"]:
            raise RhinoSpotterError(
                "RhinoSpotter bookmark commander does not match the active commander."
            )
        return _execute_sync_plan(path, loaded, state, plan, commander)


def _execute_sync_plan(path, loaded, state, plan, commander):
    expected_commander = (commander or "").strip().lower()

    # RhinoSpotter 5.5.1 revision() can miss edits to arbitrary rows because
    # its current aggregate revision is not a complete content hash. Always
    # read the local bookmarks and let stable-id fingerprints decide what
    # needs uploading. This still avoids all Community Deposits/D1 work when
    # nothing changed.
    records = loaded["records"]
    current_fingerprints = plan["current_fingerprints"]
    records_to_send = [item["record"] for item in plan["pending"]]

    systems = sorted({
        str(record.get("system")).strip()
        for record in records
        if record.get("system")
    }, key=str.casefold)

    summary = {
        "records_found": loaded["records_found"],
        "records_valid": loaded["records_valid"],
        "read_errors": loaded["read_errors"],
        "radius_inferred": loaded["radius_inferred"],
        "radius_missing": loaded["radius_missing"],
        "api_version": loaded["api_version"],
        "api_schema": loaded["api_schema"],
        "revision": loaded.get("revision"),
        "revision_unchanged": bool(
            state.get("complete")
            and state.get("revision") == loaded.get("revision")
        ),
        "records_sent": 0,
        "local_unchanged": plan["unchanged"],
        "removed_local": plan["removed_local"],
        "systems": systems,
        "inserted": 0,
        "matched": 0,
        "updated": 0,
        "unchanged": 0,
        "changed_systems": [],
        "errors": loaded["read_errors"],
        "state_saved": False,
    }

    initialize_outcomes(summary, plan)
    changed_systems: set[str] = set()
    successful_keys: set[str] = set()

    by_commander: dict[str, list[dict[str, Any]]] = {}
    for record in records_to_send:
        commander = _clean_text(record.get("commander"))
        if not commander:
            summary["errors"] += 1
            continue
        by_commander.setdefault(commander.lower(), []).append(record)

    for records in by_commander.values():
        commander = _clean_text(records[0].get("commander")) or ""
        if expected_commander and commander.lower() != expected_commander:
            raise RhinoSpotterError(
                "Bookmark commander does not match the active API profile."
            )
        api_key = get_api_key(commander)
        if not api_key:
            for record in records:
                record_sync_failure(summary, str(record["report_id"]), {"error_code":"AUTH_REQUIRED"}, record)
            continue
        throttled = False
        attempted_batch = False
        for batch in chunks(records):
            try:
                validate_batch_request(batch)
            except ValueError as exc:
                raise RhinoSpotterError(str(exc)) from exc
            if any(
                (_clean_text(record.get("commander")) or "").lower()
                != commander.lower()
                for record in batch
            ):
                raise RhinoSpotterError(
                    "Bookmark commander does not match the configured API profile."
                )
            metadata_by_report = {
                str(record["report_id"]): (
                    str(record.get("system")).strip(), _record_state_key(record)
                )
                for record in batch
            }
            if throttled:
                for record in batch:
                    record_sync_failure(summary, str(record["report_id"]), {}, record)
                continue
            if attempted_batch:
                sleep(BATCH_PAUSE_SECONDS)
            attempted_batch = True
            summary["records_sent"] += len(batch)
            try:
                result = send_deposit_batch(batch, api_key=api_key)
            except (RuntimeError, OSError, ValueError) as exc:
                throttled = "429" in str(exc)
                if throttled:
                    summary["throttled"] = True
                for record in batch:
                    record_sync_failure(summary, str(record["report_id"]), transport_failure(exc), record)
                continue
            try:
                result_by_report = validate_batch_response(batch, result)
            except ValueError:
                # An untrusted/incomplete receipt never advances fingerprints.
                for record in batch:
                    record_sync_failure(summary, str(record["report_id"]), {}, record)
                continue

            for report_id, item in result_by_report.items():
                if not item["ok"]:
                    record_sync_failure(summary, report_id, item, next(record for record in batch if str(record["report_id"]) == report_id))
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
                system, state_key = metadata_by_report[report_id]
                successful_keys.add(state_key)
                if action in {"inserted", "matched_existing_deposit", "updated_report"} and system:
                    changed_systems.add(system)

    summary["changed_systems"] = sorted(changed_systems, key=str.casefold)

    complete = not summary["pending_reports"] and not loaded["read_errors"] and not plan["commander_mismatches"] and bool(
        loaded.get("revision_stable")
    )

    try:
        with sync_state_mutex():
            latest = _get_sync_state_entry(path)
            saved_fingerprints, saved_depletion_states, saved_rejections = cache_outcomes(latest, plan, successful_keys, summary)
            state_entry = {
                "complete": complete,
                "revision": loaded.get("revision") if complete else None,
                "records_found": loaded["records_found"],
                "records_valid": loaded["records_valid"],
                "radius_inferred": loaded["radius_inferred"],
                "radius_missing": loaded["radius_missing"],
                "systems": systems,
                "fingerprints": saved_fingerprints,
                "depletion_states": saved_depletion_states,
                "rejections": saved_rejections,
            }
            _save_sync_state_entry(path, state_entry)
    except OSError as exc:
        summary["state_error"] = str(exc)
    else:
        summary["state_saved"] = True

    return summary

