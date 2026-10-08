from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
from typing import Any

from config import appname, config
from theme import theme

from EDHF_Community_Navigator.community_api import fetch_system_deposits
from EDHF_Community_Navigator.navigator import NavigatorOverlay
from EDHF_Community_Navigator.results_window import DepositsWindow
from EDHF_Community_Navigator.update_checker import check_for_update
from EDHF_Community_Navigator.rhinospotter_client import (
    RhinoSpotterNotInstalled,
    sync_bookmarks,
)


VERSION = "1.0.3"
PLUGIN_NAME = "Hotspots Finder Deposits Companion"
WORKER_EVENT = "<<EDHFCommunityNavigatorWorker>>"
NAV_X_KEY = "edhf_community_navigator_x"
NAV_Y_KEY = "edhf_community_navigator_y"
FINDER_EXE_KEY = "edhf_finder_exe_path"

plugin_name = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{plugin_name}")

_plugin_dir = ""
_frame: tk.Frame | None = None
_status: tk.Label | None = None
_sync_button: tk.Label | None = None
_scan_button: tk.Label | None = None
_open_button: tk.Label | None = None
_navigator: NavigatorOverlay | None = None
_results_window: DepositsWindow | None = None

_current_system: str | None = None
_current_body: str | None = None
_last_dashboard_status: dict[str, Any] | None = None

_cached_system: str | None = None
_cached_deposits: list[dict[str, Any]] | None = None
_deposits_cache_stale = False

_worker_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
_stopping = False
_update_check_started = False


def plugin_start3(plugin_dir: str) -> str:
    global _plugin_dir
    _plugin_dir = plugin_dir
    logger.info("Starting %s v%s", PLUGIN_NAME, VERSION)
    return PLUGIN_NAME


def plugin_app(parent: tk.Frame) -> tk.Frame:
    global _frame, _status, _sync_button, _scan_button, _open_button, _navigator

    frame = tk.Frame(parent)
    _frame = frame

    nav_x = config.get_int(NAV_X_KEY)
    nav_y = config.get_int(NAV_Y_KEY)

    # The first prototype used x=80 as its hard-coded default. Treat that
    # untouched legacy position like "no saved position" so existing testers
    # automatically migrate to the new top-centre default.
    if nav_x in (0, 80):
        nav_x = None
    if nav_y <= 0:
        nav_y = 120

    _navigator = NavigatorOverlay(
        parent,
        initial_x=nav_x,
        initial_y=nav_y,
        on_position_changed=_save_navigator_position,
    )

    heading = tk.Label(
        frame,
        text="Hotspots Finder Deposits Companion",
        font=("TkDefaultFont", 9, "bold"),
        anchor="w",
    )
    heading.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 3))

    _sync_button = _make_action_button(
        frame,
        text="Sync Bookmarks",
        command=_start_sync,
    )
    _sync_button.grid(row=1, column=0, sticky=tk.EW, padx=(0, 3))

    _scan_button = _make_action_button(
        frame,
        text="Scan System",
        command=_start_scan,
    )
    _scan_button.grid(row=1, column=1, sticky=tk.EW, padx=3)

    _open_button = _make_action_button(
        frame,
        text="Open Finder",
        command=_open_finder,
    )
    _open_button.grid(row=1, column=2, sticky=tk.EW, padx=(3, 0))

    _status = tk.Label(
        frame,
        text="Ready",
        anchor="w",
    )
    _status.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(3, 0))

    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(2, weight=1)

    frame.bind_all(WORKER_EVENT, _handle_worker_event, add="+")
    theme.update(frame)
    _update_scan_button_state()
    frame.after(1200, _start_update_check)
    return frame


def _make_action_button(
    parent: tk.Misc,
    *,
    text: str,
    command,
) -> tk.Label:
    """Create an EDMC-themed action control for dark/transparent themes."""
    button = tk.Label(
        parent,
        text=text,
        anchor=tk.CENTER,
        relief=tk.GROOVE,
        borderwidth=1,
        padx=6,
        pady=3,
    )

    def invoke(_event=None) -> None:
        if str(button.cget("state")) != str(tk.DISABLED):
            command()

    theme.button_bind(button, invoke)
    return button


def _save_navigator_position(x: int, y: int) -> None:
    # Store only the overlay position under plugin-specific keys.
    config.set(NAV_X_KEY, int(x))
    config.set(NAV_Y_KEY, int(y))


def _same_system(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().casefold() == b.strip().casefold()


def _update_scan_button_state() -> None:
    if _scan_button is None:
        return

    system = (_current_system or "").strip()
    if not system:
        _scan_button.config(text="Scan System", state=tk.DISABLED)
        return

    cache_matches = (
        _cached_deposits is not None
        and _same_system(_cached_system, system)
    )

    if not cache_matches:
        _scan_button.config(text="Scan System", state=tk.NORMAL)
    elif _deposits_cache_stale:
        _scan_button.config(text="Refresh Deposits", state=tk.NORMAL)
    elif _cached_deposits:
        _scan_button.config(text="Open Deposits", state=tk.NORMAL)
    else:
        _scan_button.config(text="No Deposits", state=tk.DISABLED)


def _close_results_window() -> None:
    global _results_window

    if _results_window is None:
        return

    try:
        if _results_window.window.winfo_exists():
            _results_window.window.destroy()
    except tk.TclError:
        pass

    _results_window = None


def _clear_system_cache(*, close_window: bool = True) -> None:
    global _cached_system, _cached_deposits, _deposits_cache_stale

    _cached_system = None
    _cached_deposits = None
    _deposits_cache_stale = False

    if close_window:
        _close_results_window()

    _update_scan_button_state()


def _set_current_system(system: str | None) -> None:
    global _current_system

    new_system = str(system or "").strip()
    if not new_system:
        return

    if _same_system(_current_system, new_system):
        _current_system = new_system
        return

    _current_system = new_system
    _clear_system_cache(close_window=True)


def plugin_stop() -> None:
    global _stopping
    _stopping = True

    if _navigator is not None:
        _navigator.destroy()

    if _frame is not None:
        try:
            _frame.unbind_all(WORKER_EVENT)
        except tk.TclError:
            pass

    logger.info("Stopped %s", PLUGIN_NAME)


def journal_entry(
    cmdr: str,
    is_beta: bool,
    system: str | None,
    station: str | None,
    entry: dict[str, Any],
    state: dict[str, Any],
) -> str | None:
    del cmdr, is_beta, station, state
    global _current_body

    event = entry.get("event")

    candidate_system = system
    if event in {"FSDJump", "CarrierJump", "Location"}:
        candidate_system = entry.get("StarSystem") or system

    if candidate_system:
        previous_system = _current_system
        _set_current_system(candidate_system)
        if not _same_system(previous_system, _current_system):
            _current_body = None

    if event == "Location":
        _current_body = entry.get("Body") or entry.get("BodyName") or _current_body
    elif event in {
        "ApproachBody",
        "Touchdown",
        "SupercruiseExit",
        "Liftoff",
    }:
        _current_body = entry.get("Body") or entry.get("BodyName") or _current_body

    return None

def dashboard_entry(
    cmdr: str,
    is_beta: bool,
    entry: dict[str, Any],
) -> None:
    del cmdr, is_beta
    global _current_body, _last_dashboard_status

    _last_dashboard_status = dict(entry)

    if entry.get("BodyName"):
        _current_body = entry.get("BodyName")

    if _navigator is not None:
        _navigator.update_status(
            entry,
            current_system=_current_system,
            current_body=_current_body,
        )


def _set_busy(busy: bool, text: str) -> None:
    state = tk.DISABLED if busy else tk.NORMAL
    if _sync_button is not None:
        _sync_button.config(state=state)
    if _scan_button is not None:
        _scan_button.config(state=tk.DISABLED if busy else tk.NORMAL)
    if _status is not None:
        _status.config(text=text)

    if not busy:
        _update_scan_button_state()


def _open_finder() -> None:
    path = config.get_str(FINDER_EXE_KEY).strip()

    if not path or not os.path.isfile(path):
        initial_dir = os.path.dirname(path) if path else ""
        path = filedialog.askopenfilename(
            parent=_frame.winfo_toplevel() if _frame is not None else None,
            title="Select ED Hotspots Finder executable",
            initialdir=initial_dir or None,
            filetypes=(
                ("Executable files", "*.exe"),
                ("All files", "*.*"),
            ),
        )

        if not path:
            if _status is not None:
                _status.config(text="Finder executable not selected")
            return

        config.set(FINDER_EXE_KEY, path)

    try:
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:
            subprocess.Popen([path])
    except Exception as exc:
        logger.exception("Could not open ED Hotspots Finder")
        config.delete(FINDER_EXE_KEY)
        if _status is not None:
            _status.config(text=f"Could not open Finder: {exc}")
        return

    if _status is not None:
        _status.config(text="ED Hotspots Finder opened")


def _start_update_check() -> None:
    global _update_check_started

    if _update_check_started or _stopping:
        return

    _update_check_started = True

    threading.Thread(
        target=_update_check_worker,
        name="EDHF-Companion-Update-Check",
        daemon=True,
    ).start()


def _update_check_worker() -> None:
    result = check_for_update(VERSION)
    _post_worker_result("update_check", result)


def _handle_update_check(result: dict[str, Any]) -> None:
    if not result.get("ok"):
        logger.debug(
            "Companion update check failed: %s",
            result.get("error") or "unknown error",
        )
        return

    if not result.get("update_available"):
        return

    latest = str(result.get("latest_version") or "").strip()
    release_url = str(result.get("release_url") or "").strip()
    if not latest or not release_url:
        return

    parent = _frame.winfo_toplevel() if _frame is not None else None

    try:
        open_release = messagebox.askyesno(
            PLUGIN_NAME,
            (
                "A new version of Hotspots Finder Deposits Companion "
                "is available.\n\n"
                f"Installed: v{VERSION}\n"
                f"Latest: v{latest}\n\n"
                "Open the GitHub release page?"
            ),
            parent=parent,
        )
    except tk.TclError:
        return

    if open_release:
        webbrowser.open_new_tab(release_url)


def _start_sync() -> None:
    if not _plugin_dir:
        _set_busy(False, "Plugin path unavailable")
        return

    _set_busy(True, "Syncing RhinoSpotter bookmarks…")
    threading.Thread(
        target=_sync_worker,
        name="EDHF-RhinoSpotter-Sync",
        daemon=True,
    ).start()


def _start_scan() -> None:
    system = (_current_system or "").strip()
    if not system:
        _set_busy(False, "Current system not available yet")
        return

    cache_matches = (
        _cached_deposits is not None
        and _same_system(_cached_system, system)
    )

    if cache_matches and not _deposits_cache_stale:
        if _cached_deposits:
            _show_deposits_window(system, _cached_deposits)
            if _status is not None:
                _status.config(
                    text=f"{system}: {len(_cached_deposits)} cached community deposits"
                )
        else:
            if _status is not None:
                _status.config(text=f"{system}: no community deposits")
        return

    action = "Refreshing" if cache_matches else "Scanning"
    _set_busy(True, f"{action} {system}…")
    threading.Thread(
        target=_scan_worker,
        args=(system,),
        name="EDHF-Community-Scan",
        daemon=True,
    ).start()

def _sync_worker() -> None:
    try:
        summary = sync_bookmarks(_plugin_dir)
    except RhinoSpotterNotInstalled as exc:
        logger.warning("%s", exc)
        _post_worker_result("sync_rhino_missing", str(exc))
    except Exception as exc:
        logger.exception("RhinoSpotter synchronization failed")
        _post_worker_result("sync_error", str(exc))
    else:
        _post_worker_result("sync_ok", summary)


def _scan_worker(system: str) -> None:
    try:
        records = fetch_system_deposits(system)
    except Exception as exc:
        logger.exception("Community Deposits scan failed")
        _post_worker_result("scan_error", (system, str(exc)))
    else:
        _post_worker_result("scan_ok", (system, records))


def _post_worker_result(kind: str, payload: Any) -> None:
    _worker_queue.put((kind, payload))

    if _stopping or config.shutting_down or _frame is None:
        return

    try:
        _frame.event_generate(WORKER_EVENT, when="tail")
    except tk.TclError:
        pass


def _handle_worker_event(_event: tk.Event | None = None) -> None:
    while True:
        try:
            kind, payload = _worker_queue.get_nowait()
        except queue.Empty:
            break

        if kind == "sync_ok":
            _handle_sync_ok(payload)
        elif kind == "sync_rhino_missing":
            _set_busy(False, payload)
        elif kind == "sync_error":
            _set_busy(False, f"Sync failed: {payload}")
        elif kind == "scan_ok":
            system, records = payload
            _handle_scan_ok(system, records)
        elif kind == "scan_error":
            system, message = payload
            _set_busy(False, f"{system}: scan failed — {message}")
        elif kind == "update_check":
            _handle_update_check(payload)


def _handle_sync_ok(summary: dict[str, Any]) -> None:
    global _deposits_cache_stale

    inserted = int(summary.get("inserted", 0) or 0)
    matched = int(summary.get("matched", 0) or 0)
    updated = int(summary.get("updated", 0) or 0)
    unchanged = int(summary.get("unchanged", 0) or 0)
    errors = int(summary.get("errors", 0) or 0)
    found = int(summary.get("records_found", 0) or 0)
    sent = int(summary.get("records_sent", 0) or 0)
    changed_systems = {
        str(system).strip().casefold()
        for system in summary.get("changed_systems", [])
        if system
    }

    if (
        _cached_deposits is not None
        and _same_system(_cached_system, _current_system)
        and _current_system
        and _current_system.strip().casefold() in changed_systems
    ):
        _deposits_cache_stale = True

    if sent == 0:
        text = (
            f"Sync: {found} bookmarks · "
            "no new or modified bookmarks"
        )
    else:
        text = (
            f"Sync: {found} bookmarks · {sent} sent · "
            f"{inserted} new · {matched} matched · "
            f"{updated} updated · {unchanged} server-unchanged"
        )

    if errors:
        text += f" · {errors} errors"

    _set_busy(False, text)


def _handle_scan_ok(system: str, records: list[dict[str, Any]]) -> None:
    global _cached_system, _cached_deposits, _deposits_cache_stale

    # Ignore a late worker result if the commander changed system meanwhile.
    if not _same_system(system, _current_system):
        _set_busy(False, f"{_current_system or 'Current system'}: ready")
        return

    _cached_system = system
    _cached_deposits = list(records)
    _deposits_cache_stale = False

    _set_busy(False, f"{system}: {len(records)} community deposits")

    # A refresh must rebuild the window from the new snapshot rather than
    # bringing an older already-open table back to the front.
    _close_results_window()

    if records:
        _show_deposits_window(system, records)


def _show_deposits_window(
    system: str,
    records: list[dict[str, Any]],
) -> None:
    global _results_window

    if _frame is None:
        return

    try:
        if (
            _results_window is not None
            and _results_window.window.winfo_exists()
        ):
            _results_window.window.deiconify()
            _results_window.window.lift()
            _results_window.window.focus_force()
            return
    except tk.TclError:
        _results_window = None

    _results_window = DepositsWindow(
        _frame,
        system=system,
        records=records,
        on_track=lambda record: _track_record(record, system),
    )

def _track_record(record: dict[str, Any], system: str) -> None:
    if _navigator is None:
        return

    enriched = dict(record)
    enriched.setdefault("system", system)
    _navigator.start(enriched, current_system=_current_system)

    # Apply the most recent Status.json snapshot immediately. Without this,
    # a newly recreated HUD had to wait for the next dashboard_entry event.
    if _last_dashboard_status is not None:
        _navigator.update_status(
            _last_dashboard_status,
            current_system=_current_system,
            current_body=_current_body,
        )

    material = (
        record.get("commodity")
        or record.get("material")
        or "deposit"
    )
    body = (
        record.get("body")
        or record.get("body_name")
        or record.get("planet_name")
        or "body"
    )
    if _status is not None:
        _status.config(text=f"Tracking {material} on {body}")
