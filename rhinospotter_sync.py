from edmc_plugin.EDHF_Community_Navigator.batch_protocol import BatchHTTPError
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from edmc_plugin.EDHF_Community_Navigator.api_credentials import get_api_key
from edmc_plugin.EDHF_Community_Navigator.sync_state_lock import sync_state_mutex
from edmc_plugin.EDHF_Community_Navigator.sync_plan import (
    load_source_module,
    record_fingerprint as _shared_record_fingerprint,
    record_state_key as _shared_record_state_key,
)


API_URL = (
    "https://ed-alliance-community-deposits."
    "littlejacket99.workers.dev/v1/deposits/batch"
)

USER_AGENT = "ED-Hotspots-Finder-Rings-and-Planets/1.0.5"

MAX_BATCH_SIZE = 5

LOCAL_APP_DATA = Path(
    os.environ.get("LOCALAPPDATA")
    or (Path.home() / "AppData" / "Local")
)

RHINOSPOTTER_ROOT = LOCAL_APP_DATA / "RhinoSpotter"

RHINOSPOTTER_PLUGIN_DIR = (
    LOCAL_APP_DATA
    / "EDMarketConnector"
    / "plugins"
    / "RhinoSpotter"
)

RS_API_PATH = RHINOSPOTTER_PLUGIN_DIR / "rs_api.py"

DATABASE_PATH = (
    RHINOSPOTTER_ROOT
    / "db"
    / "rhinospotter.db"
)

# RhinoSpotter 4.1 and older stored one JSON record per bookmark here.
# RhinoSpotter 4.2+ migrated those records into DATABASE_PATH.
CARDS_DIR = (
    RHINOSPOTTER_ROOT
    / "cards"
)

APP_DATA_DIR = (
    Path(os.environ.get("APPDATA") or Path.home())
    / "HotspotsFinder"
)

SYNC_STATE_PATH = APP_DATA_DIR / "rhinospotter_sync_state.json"
SYNC_STATE_VERSION = 1


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def make_report_id(record):
    """
    Create a stable ID for one RhinoSpotter bookmark.

    RhinoSpotter 5.3+ can edit material, rigs, amount, density and location.
    The identity therefore uses only immutable bookmark data plus RhinoSpotter's
    stable row id when available.
    """

    identity = {
        "commander": clean_text(record.get("commander")),
        "system": clean_text(record.get("system")),
        "source": "rhinospotter",
        "source_record_id": record.get("source_record_id"),
        "planet_name": clean_text(record.get("planet_name")),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "marked_at": clean_text(record.get("marked_at")),
    }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return f"rhino-{digest}"


def normalize_record(record):
    payload = {
        "report_id": make_report_id(record),
        "source": "rhinospotter",
        "source_record_id": record.get("source_record_id"),
        "commander": clean_text(record.get("commander")),
        "system": clean_text(record.get("system")),
        "system_address": record.get("system_address"),
        "planet_name": clean_text(record.get("planet_name")),
        "body_id": record.get("body_id"),
        "location_index": record.get("location_index"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "planet_radius": record.get("planet_radius"),
        "commodity": clean_text(record.get("commodity")),
        "rigs": record.get("rigs"),
        "amount": clean_text(record.get("amount")),
        "density": clean_text(record.get("density")),
        "heading": record.get("heading"),
        "marked_at": clean_text(record.get("marked_at")),
        "updated_at": clean_text(record.get("updated_at")),
    }

    # Keep absent distinct from explicit null: the API treats null as a
    # request to reactivate a previously depleted deposit.
    if "depleted_at" in record:
        payload["depleted_at"] = clean_text(record.get("depleted_at"))

    # Do not send optional null fields.
    return {
        key: value
        for key, value in payload.items()
        if value is not None or key == "depleted_at" and key in payload
    }


def _source_label(source):
    if isinstance(source, Path):
        return source.name
    return str(source)


def validate_record(record, source):
    if not isinstance(record, dict):
        raise ValueError(f"{_source_label(source)}: record is not a JSON object")

    required = [
        "system",
        "planet_name",
        "latitude",
        "longitude",
        "commodity",
    ]

    missing = [
        field
        for field in required
        if record.get(field) is None
        or record.get(field) == ""
    ]

    if missing:
        raise ValueError(
            f"{_source_label(source)}: missing fields: "
            + ", ".join(missing)
        )


def _path_key(value):
    return os.path.normcase(os.path.abspath(str(Path(value).expanduser())))


def sync_state_source_key(source_type, source_path):
    return f"{source_type}:{_path_key(source_path)}"


def load_sync_state():
    """Load the local sync cache. Corrupt/missing cache files are ignored."""

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


def get_sync_state_entry(source_type, source_path):
    state = load_sync_state()
    entry = state["sources"].get(
        sync_state_source_key(source_type, source_path),
        {},
    )
    return dict(entry) if isinstance(entry, dict) else {}


def save_sync_state_entry(source_type, source_path, entry):
    """Atomically persist one source entry without exposing bookmark data."""

    with sync_state_mutex():
        state = _load_sync_state_unlocked()
        state["sources"][
            sync_state_source_key(source_type, source_path)
        ] = dict(entry)
        _write_sync_state_unlocked(state)


def _load_sync_state_unlocked():
    try:
        state = json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": SYNC_STATE_VERSION, "sources": {}}
    if (not isinstance(state, dict) or state.get("version") != SYNC_STATE_VERSION
            or not isinstance(state.get("sources"), dict)):
        return {"version": SYNC_STATE_VERSION, "sources": {}}
    return state


def _write_sync_state_unlocked(state):
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SYNC_STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SYNC_STATE_PATH)


def record_state_key(record):
    return _shared_record_state_key(record)


def record_fingerprint(record):
    return _shared_record_fingerprint(record)


def _is_default_data_path(path):
    return _path_key(path) == _path_key(RHINOSPOTTER_ROOT)


def _rs_api_candidates(source=None):
    """Return documented RhinoSpotter API locations to try, in priority order."""

    candidates = []
    if source is not None:
        path = Path(source).expanduser()
        if path.is_file() and path.name.casefold() == "rs_api.py":
            candidates.append(path)
        elif path.is_dir():
            candidates.append(path / "rs_api.py")

        # The Settings dialog historically passes the standard data root even
        # when Auto is selected. Treat that path as automatic discovery too.
        if _is_default_data_path(path):
            candidates.insert(0, RS_API_PATH)
    else:
        candidates.append(RS_API_PATH)

    unique = []
    seen = set()
    for candidate in candidates:
        key = _path_key(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _load_rs_api_module(api_path):
    """Load RhinoSpotter's documented external API without bundling it."""

    api_path = Path(api_path).expanduser()
    if not api_path.is_file():
        raise FileNotFoundError(f"RhinoSpotter API not found: {api_path}")

    plugin_dir = str(api_path.resolve().parent)
    added_path = plugin_dir not in sys.path
    if added_path:
        sys.path.insert(0, plugin_dir)

    try:
        module = load_source_module("edhf_rhinospotter_rs_api", api_path)
    except Exception as exc:
        raise RuntimeError(
            f"Could not import RhinoSpotter API {api_path}: {exc}"
        ) from exc
    finally:
        if added_path:
            try:
                sys.path.remove(plugin_dir)
            except ValueError:
                pass

    schema = getattr(module, "SCHEMA", None)
    if schema != 1:
        raise RuntimeError(
            "Unsupported RhinoSpotter API schema "
            f"{schema!r}. This version of ED Hotspots Finder supports SCHEMA 1."
        )
    return module


def inspect_rs_api_metadata(api_path):
    """Read cheap RhinoSpotter API metadata without loading all bookmarks."""

    module = _load_rs_api_module(api_path)

    try:
        revision = module.revision()
    except Exception:
        revision = None

    try:
        api_version = str(module.version())
    except Exception:
        api_version = ""

    return {
        "revision": revision,
        "api_version": api_version,
        "api_schema": getattr(module, "SCHEMA", None),
    }


def _api_record(mark):
    """Map rs_api.bookmarks() outward keys to EDHF's stable internal names."""

    if not isinstance(mark, dict):
        return mark

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


def _body_key(record):
    system = clean_text(record.get("system"))
    body = clean_text(record.get("planet_name"))
    if not system or not body:
        return None
    return system.casefold(), body.casefold()


def _propagate_planet_radii(records):
    """Fill old missing radii from another bookmark on the same body.

    RhinoSpotter only began recording planet_radius in September 2026. A body's
    radius is stable, so one newer bookmark makes older bookmarks on that same
    (system, body) comparable without inventing a value.
    """

    known = {}
    for record in records:
        key = _body_key(record)
        radius = record.get("planet_radius") if isinstance(record, dict) else None
        if key is not None and radius not in (None, ""):
            known.setdefault(key, radius)

    inferred = 0
    missing = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("planet_radius") not in (None, ""):
            continue
        key = _body_key(record)
        radius = known.get(key) if key is not None else None
        if radius is not None:
            record["planet_radius"] = radius
            inferred += 1
        else:
            missing += 1
    return inferred, missing


def _prepare_records(items):
    """Validate raw records, propagate body radius where possible, normalize."""

    valid = []
    errors = 0
    for label, record in items:
        try:
            validate_record(record, label)
            valid.append(record)
        except Exception as exc:
            errors += 1
            print(f"[ERROR] {label}: {exc}", file=sys.stderr)

    inferred, missing = _propagate_planet_radii(valid)
    deposits = [normalize_record(record) for record in valid]
    return deposits, errors, inferred, missing


def _load_rs_api(api_path):
    module = _load_rs_api_module(api_path)

    try:
        revision_before = module.revision()
    except Exception:
        revision_before = None

    try:
        bookmarks = module.bookmarks()
    except Exception as exc:
        raise RuntimeError(f"RhinoSpotter API could not read bookmarks: {exc}") from exc

    if not isinstance(bookmarks, list):
        raise RuntimeError("RhinoSpotter API returned an unexpected bookmarks value.")

    items = []
    for index, mark in enumerate(bookmarks, start=1):
        bookmark_id = mark.get("id") if isinstance(mark, dict) else None
        label = f"rs_api bookmark #{bookmark_id or index}"
        items.append((label, _api_record(mark)))

    deposits, errors, inferred, missing = _prepare_records(items)

    try:
        revision_after = module.revision()
    except Exception:
        revision_after = revision_before

    try:
        api_version = str(module.version())
    except Exception:
        api_version = ""

    return {
        "records_found": len(bookmarks),
        "deposits": deposits,
        "read_errors": errors,
        "radius_inferred": inferred,
        "radius_missing": missing,
        "api_version": api_version,
        "api_schema": getattr(module, "SCHEMA", None),
        "revision_before": revision_before,
        "revision": revision_after,
        "revision_stable": (
            revision_before is not None
            and revision_after is not None
            and revision_before == revision_after
        ),
    }


def _database_candidates(path):
    """Return likely RhinoSpotter database locations for a path."""

    path = Path(path).expanduser()
    candidates = []

    # A saved setting from the old integration often points directly to
    # ...\RhinoSpotter\cards. Prefer the sibling 4.2+ database when present.
    if path.name.casefold() == "cards":
        candidates.append(path.parent / "db" / "rhinospotter.db")

    if path.is_dir():
        candidates.extend(
            [
                path / "db" / "rhinospotter.db",
                path / "rhinospotter.db",
            ]
        )
    elif path.suffix.casefold() == ".db":
        candidates.append(path)

    # Keep order, drop duplicates.
    unique = []
    seen = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def resolve_source(source=None):
    """Resolve RhinoSpotter to its public API first, then legacy storage.

    RhinoSpotter 5.1+ exposes rs_api.py specifically so external applications do
    not depend on its private database schema. Direct SQLite/JSON access remains
    only as a compatibility fallback for older RhinoSpotter installations.

    Accepted explicit paths:
    - RhinoSpotter plugin folder containing rs_api.py
    - rs_api.py itself
    - historical RhinoSpotter data root/db/cards paths
    """

    for candidate in _rs_api_candidates(source):
        if candidate.is_file():
            return "rs_api", candidate

    path = Path(source).expanduser() if source else RHINOSPOTTER_ROOT

    for candidate in _database_candidates(path):
        if candidate.is_file():
            return "sqlite", candidate

    legacy_candidates = []
    if path.is_dir():
        legacy_candidates.append(path / "cards")
        legacy_candidates.append(path)
    elif path.name.casefold() == "cards" and path.is_dir():
        legacy_candidates.append(path)

    if source is None:
        legacy_candidates.append(CARDS_DIR)

    seen = set()
    for candidate in legacy_candidates:
        key = _path_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_dir():
            return "legacy_json", candidate

    expected = (
        f"RhinoSpotter API: {RS_API_PATH}\n"
        f"SQLite fallback: {DATABASE_PATH}\n"
        f"Legacy cards folder: {CARDS_DIR}"
    )
    raise FileNotFoundError(
        "RhinoSpotter source not found.\n\n"
        f"Checked from: {path}\n\n{expected}"
    )

def _load_json_cards(cards_dir):
    files = sorted(Path(cards_dir).rglob("*.json"))
    items = []
    parse_errors = 0

    for path in files:
        try:
            with path.open("r", encoding="utf-8") as handle:
                record = json.load(handle)
            items.append((path, record))
        except Exception as exc:
            parse_errors += 1
            print(f"[ERROR] {path}: {exc}", file=sys.stderr)

    deposits, errors, inferred, missing = _prepare_records(items)
    return files, deposits, parse_errors + errors, inferred, missing

def load_cards(cards_dir=CARDS_DIR):
    """Legacy JSON-card loader kept for backwards compatibility."""

    cards_dir = Path(cards_dir).expanduser()
    if not cards_dir.exists():
        raise FileNotFoundError(
            f"RhinoSpotter cards folder not found: {cards_dir}"
        )

    files, deposits, _errors, _inferred, _missing = _load_json_cards(cards_dir)
    return files, deposits


def _load_database(database_path):
    database_path = Path(database_path).expanduser()
    if not database_path.is_file():
        raise FileNotFoundError(
            f"RhinoSpotter database not found: {database_path}"
        )

    try:
        uri = database_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        with closing(connection) as conn:
            conn.execute("PRAGMA query_only = ON")
            rows = conn.execute(
                "SELECT id, data FROM bookmarks ORDER BY id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Could not read RhinoSpotter database {database_path}: {exc}"
        ) from exc

    items = []
    parse_errors = 0
    for bookmark_id, raw_data in rows:
        label = f"{database_path.name}: bookmark #{bookmark_id}"
        try:
            record = json.loads(raw_data)
            if isinstance(record, dict):
                record.setdefault("source_record_id", bookmark_id)
        except Exception as exc:
            parse_errors += 1
            print(f"[ERROR] {label}: {exc}", file=sys.stderr)
            continue
        items.append((label, record))

    deposits, errors, inferred, missing = _prepare_records(items)
    return rows, deposits, parse_errors + errors, inferred, missing

def load_rhinospotter_records(source=None):
    """Load RhinoSpotter bookmarks through rs_api when available.

    Direct SQLite and legacy JSON readers are retained only for older installs.
    Missing planet radii are inherited from another bookmark on the same body
    when possible; otherwise the field remains absent/unknown rather than zero.
    """

    source_type, source_path = resolve_source(source)
    api_version = ""
    api_schema = None
    revision_before = None
    revision = None
    revision_stable = False

    if source_type == "rs_api":
        loaded = _load_rs_api(source_path)
        deposits = loaded["deposits"]
        errors = loaded["read_errors"]
        records_found = loaded["records_found"]
        inferred = loaded["radius_inferred"]
        missing = loaded["radius_missing"]
        api_version = loaded["api_version"]
        api_schema = loaded["api_schema"]
        revision_before = loaded.get("revision_before")
        revision = loaded.get("revision")
        revision_stable = bool(loaded.get("revision_stable"))
    elif source_type == "sqlite":
        rows, deposits, errors, inferred, missing = _load_database(source_path)
        records_found = len(rows)
    else:
        files, deposits, errors, inferred, missing = _load_json_cards(source_path)
        records_found = len(files)

    return {
        "source_type": source_type,
        "source_path": source_path,
        "records_found": records_found,
        "records_valid": len(deposits),
        "read_errors": errors,
        "radius_inferred": inferred,
        "radius_missing": missing,
        "api_version": api_version,
        "api_schema": api_schema,
        "revision_before": revision_before,
        "revision": revision,
        "revision_stable": revision_stable,
        "deposits": deposits,
    }

def send_batch(deposits, api_key=None):
    if not api_key:
        commanders = {clean_text(item.get("commander")) for item in deposits}
        commanders.discard(None)
        if len(commanders) != 1:
            raise RuntimeError("An API key is required for the bookmark commander.")
        commander = next(iter(commanders))
        api_key = get_api_key(commander)
    if not api_key:
        raise RuntimeError("No API key is configured for the bookmark commander.")
    payload = {
        "deposits": deposits
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as exc:
        raise BatchHTTPError(
            f"Community Deposits API returned HTTP {exc.code}.", status=exc.code
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError(
            "Community Deposits batch upload failed due to a network error."
        ) from None


def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize RhinoSpotter bookmarks with "
            "ED Alliance Community Deposits."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and prepare records without sending them to the server.",
    )

    parser.add_argument(
        "--source",
        help=(
            "Optional RhinoSpotter plugin/API or legacy data path. "
            "By default rs_api is preferred, with SQLite/JSON fallback."
        ),
    )

    args = parser.parse_args()

    # The command-line utility follows the same preview/confirm contract as the
    # GUIs. It is intentionally interactive unless --dry-run is supplied.
    from rhinospotter_sync_service import confirm_sync, preview_sync

    plan = preview_sync(args.source)
    pending = plan.get("preview_pending", [])
    print(f"Source type: {plan.get('source_type', 'unknown')}")
    print(f"Source: {plan.get('source_path', '')}")
    print(f"Commander: {plan.get('commander') or '(unknown)'}")
    print(f"Records found: {plan.get('records_found', 0)}")
    print(f"Valid records: {plan.get('records_valid', 0)}")
    print(f"New: {plan.get('new', 0)}")
    print(f"Modified: {plan.get('modified', 0)}")
    print(f"Unchanged: {plan.get('unchanged', 0)}")
    print(f"Skipped: {plan.get('skipped', 0)}")
    if plan.get("credential_missing"):
        print(f"Records skipped for missing API credentials: {plan['credential_missing']}")

    for index, item in enumerate(pending, start=1):
        deposit = item["record"]
        print(
            f"[{index}] {item['status']} | {deposit.get('system')} | "
            f"{deposit.get('planet_name')} | {deposit.get('commodity')} | "
            f"report_id: {deposit.get('report_id')}"
        )

    if args.dry_run:
        print("DRY RUN: no data sent.")
        return
    if not pending:
        print("No eligible new or modified records to synchronize.")
        return

    try:
        answer = input("Type SYNC to confirm sending these records: ").strip()
    except EOFError:
        answer = ""
    if answer != "SYNC":
        print("Synchronization cancelled; no data sent.")
        return

    result = confirm_sync(args.source, plan["snapshot"])
    if result.get("stale"):
        print("The source or sync state changed. Review a new preview before syncing.")
        return

    from edmc_plugin.EDHF_Community_Navigator.batch_protocol import sync_failure_text
    partial = bool(result.get("errors") or result.get("state_error"))
    print("Synchronization partial." if partial else "Synchronization completed.")
    print(f"New deposits: {result.get('inserted', 0)}")
    print(f"Reports matched to existing deposits: {result.get('matched', 0)}")
    print(f"Updated reports: {result.get('updated', 0)}")
    print(f"Unchanged reports: {result.get('unchanged', 0)}")
    print(f"Errors: {result.get('errors', 0)}")
    if partial:
        print(sync_failure_text(result))


if __name__ == "__main__":
    main()
