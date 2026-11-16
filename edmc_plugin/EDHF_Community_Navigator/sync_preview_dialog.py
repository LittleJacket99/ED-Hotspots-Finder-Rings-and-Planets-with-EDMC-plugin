"""Compact modal confirmation dialog for RhinoSpotter sync plans."""

from __future__ import annotations

import tkinter as tk
import logging
from tkinter import ttk
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _usable_parent_bounds(parent, screen_w: int, screen_h: int):
    """Return parent bounds only when its normal/zoomed window is usable."""
    try:
        parent_window = parent.winfo_toplevel()
        state = parent_window.state()
        mapped = parent_window.winfo_ismapped()
        px, py = parent_window.winfo_rootx(), parent_window.winfo_rooty()
        pw, ph = parent_window.winfo_width(), parent_window.winfo_height()
        if (
            state in {"normal", "zoomed"}
            and mapped
            and pw > 1
            and ph > 1
            and 0 <= px < screen_w
            and 0 <= py < screen_h
            and px + pw > 0
            and py + ph > 0
        ):
            return px, py, pw, ph
    except Exception:
        # A destroyed, withdrawn, or otherwise unavailable parent falls back
        # to the primary screen center.
        pass
    return None


def _centered_geometry(parent, width: int, height: int, screen_w: int, screen_h: int) -> str:
    """Center on a usable parent, otherwise on screen, keeping the dialog visible."""
    margin = min(16, max(0, (screen_w - 1) // 2), max(0, (screen_h - 1) // 2))
    width = min(max(1, width), max(1, screen_w - 2 * margin))
    height = min(max(1, height), max(1, screen_h - 2 * margin))

    bounds = _usable_parent_bounds(parent, screen_w, screen_h)
    if bounds is not None:
        px, py, pw, ph = bounds
        x = px + (pw - width) // 2
        y = py + (ph - height) // 2
    else:
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2

    x = max(margin, min(x, screen_w - width - margin))
    y = max(margin, min(y, screen_h - height - margin))
    return f"{width}x{height}+{x}+{y}"


def show_sync_preview(
    parent: tk.Misc,
    plan: dict[str, Any],
    *,
    palette: dict[str, str] | None = None,
    apply_theme: Callable[[tk.Widget], None] | None = None,
    position_window: Callable[[tk.Toplevel], None] | None = None,
    button_factory: Callable[..., tk.Widget] | None = None,
    message_factory: Callable[..., tk.Widget] | None = None,
) -> bool:
    """Return True only after explicit confirmation; closing is Cancel."""
    if message_factory is not None:
        from .edmc_sync_dialog import show_edmc_sync_preview
        return show_edmc_sync_preview(parent, plan, palette=palette, apply_theme=apply_theme,
                                      position_window=position_window, button_factory=button_factory,
                                      message_factory=message_factory)
    palette = palette or {}
    # Finder keeps its existing labels and layout; EDMC supplies its own widget.
    message_factory = message_factory or tk.Label
    bg = palette.get("panel", palette.get("background", parent.cget("background")))
    surface = palette.get("panel2", palette.get("background", bg))
    fg = palette.get("text", palette.get("foreground", "#202020"))
    muted = palette.get("muted", "#606060")
    accent = palette.get("accent", palette.get("selected_bg", "#2878c8"))
    hover = palette.get("hover", palette.get("selected_bg", accent))
    line = palette.get("line2", palette.get("border", "#888888"))
    font_family = palette.get("font_family", "TkDefaultFont")

    window = tk.Toplevel(parent)
    # Prevent Tk from mapping the toplevel at its default position while its
    # widgets and final geometry are still being established.
    window.withdraw()
    window.title("Confirm Synchronization")
    window.resizable(False, False)
    window.configure(background=bg)
    result = {"confirmed": False}
    closing = {"value": False}
    grab_acquired = {"value": False}

    def close_dialog(confirmed: bool = False) -> None:
        if closing["value"]:
            return
        closing["value"] = True
        result["confirmed"] = confirmed
        if grab_acquired["value"]:
            try:
                window.grab_release()
            except tk.TclError:
                pass
            grab_acquired["value"] = False
        try:
            if window.winfo_exists():
                window.destroy()
        except tk.TclError:
            pass

    outer = tk.Frame(window, bg=bg, padx=20, pady=16)
    outer.grid(row=0, column=0, sticky="nsew")
    outer.columnconfigure(0, weight=1)

    commander = str(plan.get("commander") or "(missing)")
    tk.Label(
        outer, text="Commander", bg=bg, fg=muted, anchor="center",
        font=(font_family, 9),
    ).grid(row=0, column=0, sticky="ew")
    commander_label = message_factory(
        outer, text=commander, bg=bg, fg=fg, anchor="center",
        font=(font_family, 12, "bold"), wraplength=390,
    )
    commander_label.grid(row=1, column=0, sticky="ew", pady=(1, 12))

    counts = tk.Frame(outer, bg=bg)
    counts.grid(row=2, column=0, sticky="ew")
    for column in range(3):
        counts.columnconfigure(column, weight=1, uniform="sync-count")
    for column, (label, key) in enumerate((
        ("New", "new"), ("Modified", "modified"), ("Unchanged", "unchanged"),
    )):
        card = tk.Frame(
            counts, bg=surface, highlightbackground=line, highlightthickness=1,
            padx=8, pady=7,
        )
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))
        card.columnconfigure(0, weight=1)
        tk.Label(
            card, text=str(int(plan.get(key, 0) or 0)), bg=surface, fg=fg,
            anchor="center", font=(font_family, 14, "bold"),
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            card, text=label, bg=surface, fg=muted, anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

    ready = int(plan.get("new", 0) or 0) + int(plan.get("modified", 0) or 0)
    missing_credentials = int(plan.get("credential_missing", 0) or 0)
    if ready:
        noun = "deposit" if ready == 1 else "deposits"
        primary_message = f"{ready} {noun} ready to sync."
    elif missing_credentials:
        noun = "deposit needs" if missing_credentials == 1 else "deposits need"
        primary_message = f"{missing_credentials} {noun} API credentials before syncing."
    elif plan.get("skipped"):
        primary_message = f"{plan['skipped']} Skipped; source changes are required before these versions can be uploaded."
    else:
        primary_message = "All deposits are up to date"
    message_factory(
        outer, text=primary_message, bg=bg, fg=fg, anchor="center",
        justify="center", wraplength=390,
    ).grid(row=3, column=0, sticky="ew", pady=(12, 0))

    warnings = []
    skipped = int(plan.get("skipped", 0) or 0)
    if missing_credentials and ready:
        noun = "deposit" if missing_credentials == 1 else "deposits"
        warnings.append(f"API credentials missing for {missing_credentials} {noun}.")
    if skipped:
        warnings.append(f"Skipped records: {skipped}.")
        from .batch_protocol import sync_failure_text
        reason = sync_failure_text({"skipped_reports": plan.get("skipped_reports", [])})
        if reason:
            warnings.append(reason)
    if plan.get("confirm_blocked") and not int(
        plan.get("commander_mismatches", 0) or 0
    ):
        warnings.append("Synchronization is unavailable until the Commander is verified.")
    if warnings:
        message_factory(
            outer, text="\n".join(warnings), bg=bg, fg=muted,
            anchor="center", justify="center", wraplength=390,
        ).grid(row=4, column=0, sticky="ew", pady=(7, 0))

    buttons = tk.Frame(outer, bg=bg)
    buttons.grid(row=5, column=0, sticky="e", pady=(14, 0))

    def accept() -> None:
        close_dialog(confirmed=True)

    if button_factory is not None:
        # EDMC's results window uses ttk.Button, whose style follows the
        # active EDMC theme automatically. Finder keeps its palette buttons.
        confirm = button_factory(buttons, text="Confirm Sync", command=accept)
        cancel = button_factory(buttons, text="Cancel", command=close_dialog)
    else:
        confirm = tk.Button(
            buttons, text="Confirm Sync", command=accept,
            bg=accent, fg=fg, activebackground=hover, activeforeground=fg,
            relief="flat", padx=12, pady=5,
        )
        cancel = tk.Button(
            buttons, text="Cancel", command=close_dialog,
            bg=surface, fg=fg, activebackground=hover, activeforeground=fg,
            relief="flat", padx=12, pady=5,
        )
    cancel.pack(side="right", padx=(7, 0))
    confirm.pack(side="right")

    if not confirmation_enabled(plan):
        if button_factory is not None:
            confirm.configure(state=tk.DISABLED)
        else:
            confirm.configure(
                state=tk.DISABLED, bg=surface, fg=muted,
                activebackground=surface, activeforeground=muted,
                disabledforeground=muted,
            )

    window.protocol("WM_DELETE_WINDOW", close_dialog)
    if apply_theme is not None:
        try:
            # EDMC's theme API accepts Tk widgets (Frame, Label, Button, ...),
            # while Toplevel is a separate Tkinter window class.
            apply_theme(outer)
        except Exception:
            # The explicit palette already styles the dialog. A host theme
            # failure must not abort preview creation or strand a hidden window.
            logger.exception("Could not apply host theme to sync preview")
    window.update_idletasks()

    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    max_width = max(1, screen_w - 32)
    max_height = max(1, screen_h - 48)
    width = min(max(window.winfo_reqwidth(), min(420, max_width)), max_width)
    height = min(max(window.winfo_reqheight(), min(230, max_height)), max_height)
    if _usable_parent_bounds(parent, screen_w, screen_h) is not None:
        window.transient(parent.winfo_toplevel())
    else:
        # A transient owned by an iconic/withdrawn EDMC window may be hidden
        # with it, defeating the primary-screen fallback.
        window.transient("")
    window.geometry(_centered_geometry(parent, width, height, screen_w, screen_h))
    if position_window is not None:
        try:
            position_window(window)
        except Exception:
            # Keep the calculated centered geometry if host-specific geometry
            # information becomes unavailable during startup, and retain the
            # full traceback for host diagnostics.
            logger.exception("Could not apply host positioning to sync preview")

    try:
        window.deiconify()
        window.update_idletasks()
        window.grab_set()
        grab_acquired["value"] = True
        window.lift()
        window.focus_force()
        parent.wait_window(window)
    finally:
        # Covers external destroy, WM close, and exceptions while waiting.
        if grab_acquired["value"]:
            try:
                window.grab_release()
            except tk.TclError:
                pass
            grab_acquired["value"] = False
        if not closing["value"]:
            close_dialog()
    return result["confirmed"]


def confirmation_enabled(plan: dict[str, Any]) -> bool:
    """Only permit confirmation when the displayed plan is actually sendable."""
    changes_available = bool(
        int(plan.get("new", 0) or 0) + int(plan.get("modified", 0) or 0)
    )
    credentials_present = int(plan.get("credential_missing", 0) or 0) == 0
    return changes_available and credentials_present and not bool(
        plan.get("confirm_blocked")
    )
