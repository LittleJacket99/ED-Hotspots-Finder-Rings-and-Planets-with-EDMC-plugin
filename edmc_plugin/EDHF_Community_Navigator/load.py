from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Any

from config import appname, config
from theme import theme

from EDHF_Community_Navigator.community_api import fetch_system_deposits
from EDHF_Community_Navigator.api_credentials import store_api_key
from EDHF_Community_Navigator.navigator import NavigatorOverlay
from EDHF_Community_Navigator.results_window import DepositsWindow, theme_colours
from EDHF_Community_Navigator.update_checker import check_for_update
from EDHF_Community_Navigator.rhinospotter_client import (
    RhinoSpotterNotInstalled,
    confirm_sync,
    preview_sync,
)
from EDHF_Community_Navigator.sync_preview_dialog import show_sync_preview
from EDHF_Community_Navigator.message_label import MessageLabel
from EDHF_Community_Navigator.dialog_layout import DialogBody
from EDHF_Community_Navigator.section_order import SectionOrder, attach_tooltip


VERSION = "1.0.5"
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
_credentials_window: tk.Toplevel | None = None

_current_system: str | None = None
_current_body: str | None = None
_current_commander: str | None = None
_last_dashboard_status: dict[str, Any] | None = None

_cached_system: str | None = None
_cached_deposits: list[dict[str, Any]] | None = None
_deposits_cache_stale = False

_worker_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
_stopping = False
_update_check_started = False
_status_report_inflight = None
_commander_generation = 0
_cached_status_report_allowed = False
_section_order = None
_ui_busy = False


def plugin_start3(plugin_dir: str) -> str:
    global _plugin_dir
    _plugin_dir = plugin_dir
    logger.info("Starting %s v%s", PLUGIN_NAME, VERSION)
    return PLUGIN_NAME


def plugin_app(parent: tk.Frame) -> tk.Frame:
    global _frame, _status, _sync_button, _scan_button, _open_button, _navigator, _section_order

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

    heading_row = tk.Frame(frame)
    heading_row.grid(row=0, column=0, columnspan=3, sticky=tk.EW, pady=(0, 3))
    heading_row.columnconfigure(0, weight=1)
    heading = tk.Label(
        heading_row,
        text="Alliance Community Deposits",
        font=("TkDefaultFont", 9, "bold"),
        anchor="w",
    )
    heading.grid(row=0, column=0, sticky=tk.W)
    controls = tk.Frame(heading_row)
    controls.grid(row=0, column=1, sticky=tk.E)
    _section_order = SectionOrder(frame, config,
                                  is_busy=lambda: _ui_busy or _status_report_inflight is not None or _stopping)
    arrows = []
    for column, (glyph, step, tooltip) in enumerate((("▲", -1, "Move up"), ("▼", 1, "Move down"))):
        arrow = tk.Label(controls, text=glyph, width=1, padx=1, pady=0, borderwidth=0,
                         font=("TkDefaultFont", 8), takefocus=True)
        arrow.grid(row=0, column=column, padx=(0, 1 if column == 0 else 0))

        def move(_event=None, direction=step):
            _section_order.move(direction)
        theme.button_bind(arrow, move)
        arrow.bind("<Return>", move)
        arrow.bind("<space>", move)
        attach_tooltip(arrow, tooltip)
        arrows.append(arrow)
    _section_order.attach(*arrows)

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

    _status = MessageLabel(
        frame,
        text="Ready",
        anchor="w",
    )
    _status.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=(3, 0))

    credentials_button = _make_action_button(
        frame, text="Configure Community API Keys", command=_open_credentials_dialog
    )
    credentials_button.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(3, 0))

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
    if _section_order is not None:
        _section_order.close()

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
    del is_beta, station, state
    global _current_body, _current_commander

    if cmdr:
        _set_report_commander(str(cmdr).strip())

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
    del is_beta
    global _current_body, _current_commander, _last_dashboard_status

    if cmdr:
        _set_report_commander(str(cmdr).strip())

    _last_dashboard_status = dict(entry)

    if entry.get("BodyName"):
        _current_body = entry.get("BodyName")

    if _navigator is not None:
        _navigator.update_status(
            entry,
            current_system=_current_system,
            current_body=_current_body,
        )


def _status_commander_key(commander):
    from EDHF_Community_Navigator.community_api import commander_identity
    return commander_identity(commander)


def _set_report_commander(commander):
    global _current_commander, _commander_generation, _cached_deposits, _cached_system, _cached_status_report_allowed
    if _status_commander_key(_current_commander) != _status_commander_key(commander):
        _commander_generation += 1
        _close_results_window()
        _cached_deposits = None
        _cached_system = None
        _cached_status_report_allowed = False
    _current_commander = commander


def _has_pending_status_report():
    if not _current_commander:
        return False
    from EDHF_Community_Navigator.status_reports import load_pending
    try:
        return load_pending(_current_commander) is not None
    except Exception:
        # Open the window to show the storage error, without enabling a send.
        return True


def _status_report_available(commander, generation):
    from EDHF_Community_Navigator.api_credentials import get_api_key
    return (generation == _commander_generation and _status_commander_key(commander) == _status_commander_key(_current_commander)
            and _status_report_inflight is None and _cached_status_report_allowed and bool(get_api_key(commander)))


def _start_status_report(commander, generation, record=None, state=None):
    global _status_report_inflight
    from EDHF_Community_Navigator.status_reports import load_pending, prepare_operation
    if not _status_report_available(commander, generation):
        return
    try:
        pending = load_pending(commander)
        if record is not None:
            if pending or record.get("_can_report_state") is not True:
                raise RuntimeError("A report is pending or Write permission is unavailable.")
            pending = prepare_operation(commander, record.get("id"), state)
        if pending is None:
            return
    except Exception:
        if _results_window:
            _results_window.report_message.configure(text="Cannot prepare status report. Check the pending operation and credentials.")
        return
    _status_report_inflight = (commander, generation)
    if globals().get("_section_order") is not None:
        _section_order.refresh()
    if _results_window:
        _results_window.pending = pending
        _results_window.report_busy = True
        _results_window.report_message.configure(text=f"Sending {pending['state'].title()} report for deposit {pending['deposit_id']}…")
        _results_window.refresh_report_controls()
    threading.Thread(target=_status_report_worker, args=(commander, generation),
                     name="EDHF-Status-Report", daemon=True).start()


def _status_report_worker(commander, generation):
    from EDHF_Community_Navigator.status_reports import submit_pending, StatusReportError
    try:
        event = submit_pending(commander)
    except StatusReportError as exc:
        _post_worker_result("status_report", (commander, generation, None, str(exc), exc.status))
    except Exception:
        _post_worker_result("status_report", (commander, generation, None,
            "Status report outcome not confirmed. Check the pending operation before retrying.", None))
    else:
        _post_worker_result("status_report", (commander, generation, event, None, None))


def _handle_status_report_result(payload):
    global _status_report_inflight, _cached_status_report_allowed
    commander, generation, event, error, status = payload
    if _status_report_inflight == (commander, generation):
        _status_report_inflight = None
    if globals().get("_section_order") is not None:
        _section_order.refresh()
    if generation != _commander_generation or _status_commander_key(commander) != _status_commander_key(_current_commander):
        # Release availability, without applying the old session's data/message.
        if _results_window is not None and _status_report_inflight is None:
            _results_window.report_busy = False
            from EDHF_Community_Navigator.status_reports import load_pending
            try:
                _results_window.pending = load_pending(_current_commander)
            except Exception:
                _results_window.report_busy = True
            _results_window.refresh_report_controls()
        return
    from EDHF_Community_Navigator.status_reports import load_pending, pending_report_message
    if event and _cached_deposits is not None:
        for record in _cached_deposits:
            if record.get("id") == event["deposit_id"]:
                previous = record.get("latest_direct_state_event") or {}
                if previous.get("id", 0) < event["id"]:
                    record["latest_direct_state_event"] = {k: event[k] for k in ("id", "state", "commander", "recorded_at")}
                if isinstance(event.get("shared_state"), dict):
                    record["shared_state"] = event["shared_state"]
    if _results_window is not None:
        try:
            _results_window.pending = load_pending(commander)
        except Exception:
            _results_window.report_message.configure(text="Cannot read pending status report. No new report will be sent.")
            _results_window.report_busy = True
            _results_window.refresh_report_controls()
            return
        _results_window.report_busy = False
        if status == 403:
            _cached_status_report_allowed = False
            for record in _results_window.records:
                record["_can_report_state"] = False
        if error and _results_window.pending:
            message = pending_report_message(status, error)
        else:
            message = error or f"Status report recorded: {event['state'].title()} — deposit {event['deposit_id']}."
        _results_window.report_message.configure(text=message)
        _results_window.refresh_report_controls()


def _set_busy(busy: bool, text: str) -> None:
    global _ui_busy
    _ui_busy = busy
    if globals().get("_section_order") is not None:
        _section_order.refresh()
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
    if not _current_commander:
        _set_busy(False, "Commander not available yet")
        return

    _set_busy(True, "Preparing RhinoSpotter sync preview…")
    commander = _current_commander
    threading.Thread(
        target=_sync_preview_worker,
        args=(commander,),
        name="EDHF-RhinoSpotter-Sync",
        daemon=True,
    ).start()


def _credentials_changed(commander):
    """Fail closed immediately, then verify through the authenticated catalog GET."""
    global _commander_generation, _cached_status_report_allowed, _cached_deposits, _cached_system, _deposits_cache_stale
    _commander_generation += 1
    generation = _commander_generation
    _cached_status_report_allowed = False
    _cached_deposits = None
    _cached_system = None
    _deposits_cache_stale = True
    if _results_window is not None:
        for record in _results_window.records:
            record["_can_report_state"] = False
        _results_window.report_message.configure(text="Verifying the new API Key…")
        _results_window.refresh_report_controls()
    _set_busy(True, "Verifying the new API Key…")
    threading.Thread(target=_scan_worker, args=(_current_system or "", commander, generation),
                     name="EDHF-Credential-Check", daemon=True).start()


def _open_credentials_dialog() -> None:
    global _credentials_window

    commander = (_current_commander or "").strip()
    if not commander:
        messagebox.showerror(PLUGIN_NAME, "Commander is not available yet.", parent=_frame)
        return

    parent = _frame.winfo_toplevel()
    existing = _credentials_window
    if existing is not None:
        try:
            if existing.winfo_exists():
                _center_credentials_window(existing, parent)
                existing.deiconify()
                existing.lift()
                existing.grab_set()
                existing.focus_force()
                return
        except tk.TclError:
            pass

    window = tk.Toplevel(_frame)
    _credentials_window = window
    window.withdraw()
    window.title("Community Deposits API Key")
    window.resizable(False, False)
    window.transient(parent)
    layout = DialogBody(window, background=window.cget("background"))
    content = layout.content
    content.columnconfigure(1, weight=1)
    MessageLabel(content, text=f"Commander: {commander}", anchor="w").grid(
        row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6)
    )
    tk.Label(content, text="API Key").grid(row=1, column=0, sticky="w", padx=12, pady=4)
    api_key_entry = tk.Entry(content, width=42, show="*")
    api_key_entry.grid(row=1, column=1, sticky="ew", padx=12, pady=4)
    MessageLabel(
        content,
        text=("Use a key with can_read=1 and can_write=1. Leave blank to keep "
              "the saved key. It is stored in shared Windows Credential Manager."),
        justify="left",
    ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=6)

    def save_key() -> None:
        changed = bool(api_key_entry.get())
        try:
            if changed:
                store_api_key(commander, api_key_entry.get())
        except (OSError, ValueError) as exc:
            messagebox.showerror(PLUGIN_NAME, str(exc), parent=window)
            return
        api_key_entry.delete(0, tk.END)
        window.destroy()
        if changed:
            _credentials_changed(commander)

    tk.Button(layout.footer, text="Save API Key", command=save_key).pack(side="right")

    layout.fit(parent)
    _center_credentials_window(window, parent)
    window.deiconify()
    window.update_idletasks()
    _center_credentials_window(window, parent)
    window.grab_set()
    window.lift()
    window.focus_force()


def _center_credentials_window(window: tk.Toplevel, parent: tk.Misc) -> None:
    """Center the credential dialog on EDMC, with a screen-centred fallback."""
    try:
        parent.update_idletasks()
        window.update_idletasks()
        width = max(window.winfo_reqwidth(), window.winfo_width())
        height = max(window.winfo_reqheight(), window.winfo_height())
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()

        center_x = screen_width // 2
        center_y = screen_height // 2
        try:
            if (
                parent.winfo_exists()
                and parent.winfo_ismapped()
                and parent.state() == "normal"
                and parent.winfo_width() > 1
                and parent.winfo_height() > 1
            ):
                center_x = parent.winfo_rootx() + parent.winfo_width() // 2
                center_y = parent.winfo_rooty() + parent.winfo_height() // 2
        except tk.TclError:
            pass

        # Reserve room for native title-bar/border decorations when clamping.
        margin_x = 24
        margin_y = 40

        def clamp(position: int, extent: int, size: int, margin: int) -> int:
            if size + margin * 2 > extent:
                return min(max(0, position), max(0, extent - size))
            return min(max(margin, position), extent - size - margin)

        x = clamp(center_x - width // 2, screen_width, width, margin_x)
        y = clamp(center_y - height // 2, screen_height, height, margin_y)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.update_idletasks()

        if window.state() != "withdrawn":
            # Tk reports the client origin after the WM applies decorations.
            # Correct any offset and clamp again to keep the visible window in
            # bounds. The first pass runs while withdrawn to avoid a top-left flash.
            actual_width = max(width, window.winfo_width())
            actual_height = max(height, window.winfo_height())
            x += center_x - (window.winfo_rootx() + actual_width // 2)
            y += center_y - (window.winfo_rooty() + actual_height // 2)
            x = clamp(x, screen_width, actual_width, margin_x)
            y = clamp(y, screen_height, actual_height, margin_y)
            window.geometry(f"+{x}+{y}")
            window.update_idletasks()
    except tk.TclError:
        # Keep the dialog usable if the WM cannot provide geometry information.
        pass


def _start_scan() -> None:
    system = (_current_system or "").strip()
    if not system:
        _set_busy(False, "Current system not available yet")
        return
    if not _current_commander:
        _set_busy(False, "Commander not available yet")
        return

    cache_matches = (
        _cached_deposits is not None
        and _same_system(_cached_system, system)
    )

    if cache_matches and not _deposits_cache_stale:
        if _cached_deposits or _has_pending_status_report():
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
        args=(system, _current_commander, _commander_generation),
        name="EDHF-Community-Scan",
        daemon=True,
    ).start()

def _sync_preview_worker(commander: str) -> None:
    try:
        plan = preview_sync(_plugin_dir, commander=commander)
    except RhinoSpotterNotInstalled as exc:
        logger.warning("%s", exc)
        _post_worker_result("sync_rhino_missing", str(exc))
    except Exception as exc:
        logger.exception("RhinoSpotter preview failed")
        _post_worker_result("sync_error", str(exc))
    else:
        _post_worker_result("sync_preview", (commander, plan))


def _sync_worker(commander: str, expected_snapshot: str) -> None:
    try:
        summary = confirm_sync(
            _plugin_dir, commander=commander,
            expected_snapshot=expected_snapshot,
        )
    except Exception as exc:
        logger.exception("RhinoSpotter synchronization failed")
        _post_worker_result("sync_error", str(exc))
    else:
        if summary.get("stale"):
            _post_worker_result("sync_stale", (commander, summary["plan"]))
        else:
            _post_worker_result("sync_ok", summary)


def _scan_worker(system: str, commander: str, generation: int) -> None:
    try:
        records = fetch_system_deposits(system or "__credential_check__", commander=commander)
    except Exception as exc:
        logger.exception("Community Deposits scan failed")
        _post_worker_result("scan_error", (system, commander, generation, str(exc)))
    else:
        _post_worker_result("scan_ok", (system, commander, generation, records))


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

        if kind == "status_report":
            _handle_status_report_result(payload)
        elif kind == "sync_ok":
            _handle_sync_ok(payload)
        elif kind in {"sync_preview", "sync_stale"}:
            _handle_sync_preview(payload)
        elif kind == "sync_rhino_missing":
            _set_busy(False, payload)
        elif kind == "sync_error":
            _set_busy(False, f"Sync failed: {payload}")
        elif kind == "scan_ok":
            system, commander, generation, records = payload
            if generation == _commander_generation and _status_commander_key(commander) == _status_commander_key(_current_commander):
                _handle_scan_ok(system, records)
        elif kind == "scan_error":
            system, commander, generation, message = payload
            if generation == _commander_generation and _status_commander_key(commander) == _status_commander_key(_current_commander):
                _set_busy(False, f"{system}: scan failed — {message}")
                if _results_window is not None:
                    _results_window.report_message.configure(text="API Key could not be verified. Check credentials or connection.")
                    _results_window.refresh_report_controls()
        elif kind == "update_check":
            _handle_update_check(payload)


def _handle_sync_preview(payload) -> None:
    commander, plan = payload
    active_commander = (_current_commander or "").strip()
    if not active_commander:
        _set_busy(False, "Commander not available; sync cancelled")
        return
    if active_commander.casefold() != commander.casefold():
        threading.Thread(
            target=_sync_preview_worker,
            args=(active_commander,),
            name="EDHF-RhinoSpotter-Preview",
            daemon=True,
        ).start()
        return
    parent = _frame.winfo_toplevel() if _frame is not None else None
    if parent is None:
        _set_busy(False, "Sync cancelled")
        return
    try:
        confirmed = show_sync_preview(
            parent,
            plan,
            palette=theme_colours(),
            apply_theme=theme.update,
            button_factory=ttk.Button,
            message_factory=MessageLabel,
            position_window=lambda window: _center_credentials_window(window, parent),
        )
    except Exception:
        # A failed preview must not leave EDMC's actions disabled. The shared
        # dialog owns grab cleanup; this restores the plugin's busy state.
        logger.exception("Could not open RhinoSpotter sync confirmation")
        _set_busy(False, "Sync preview unavailable")
        return
    if not confirmed:
        _set_busy(False, "Sync cancelled")
        return
    active_commander = (_current_commander or "").strip()
    if not active_commander:
        _set_busy(False, "Commander not available; sync cancelled")
        return
    if active_commander.casefold() != commander.casefold():
        threading.Thread(
            target=_sync_preview_worker,
            args=(active_commander,),
            name="EDHF-RhinoSpotter-Preview",
            daemon=True,
        ).start()
        return
    threading.Thread(
        target=_sync_worker,
        args=(commander, plan["snapshot"]),
        name="EDHF-RhinoSpotter-Sync",
        daemon=True,
    ).start()


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

    from .message_label import sync_message
    _set_busy(False, sync_message(summary))


def _handle_scan_ok(system: str, records: list[dict[str, Any]]) -> None:
    global _cached_system, _cached_deposits, _deposits_cache_stale, _cached_status_report_allowed

    if not system and not _current_system:
        _cached_status_report_allowed = bool(getattr(records, "can_report_state", False))
        _set_busy(False, "API Key verified")
        return
    # Ignore a late worker result if the commander changed system meanwhile.
    if not _same_system(system, _current_system):
        _set_busy(False, f"{_current_system or 'Current system'}: ready")
        return

    _cached_system = system
    _cached_deposits = list(records)
    _cached_status_report_allowed = bool(getattr(records, "can_report_state", False))
    _deposits_cache_stale = False

    _set_busy(False, f"{system}: {len(records)} community deposits")

    # A refresh must rebuild the window from the new snapshot rather than
    # bringing an older already-open table back to the front.
    _close_results_window()

    if records or _has_pending_status_report():
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

    commander = (_current_commander or "").strip()
    generation = _commander_generation
    from EDHF_Community_Navigator.status_reports import load_pending, pending_report_message
    pending_error = False
    try:
        pending = load_pending(commander) if commander else None
    except Exception:
        pending = None
        pending_error = True

    _results_window = DepositsWindow(
        _frame,
        system=system,
        records=records,
        on_track=lambda record: _track_record(record, system),
        on_report=lambda record, state: _start_status_report(commander, generation, record, state),
        on_retry=lambda: _start_status_report(commander, generation),
        pending=pending,
        report_available=lambda: not pending_error and _status_report_available(commander, generation),
    )
    if pending_error:
        _results_window.report_message.configure(text="Cannot read pending status report. No new report will be sent.")
    elif pending:
        _results_window.report_message.configure(text=pending_report_message())
    _results_window.refresh_report_controls()


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
