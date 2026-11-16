"""EDMC-only sync preview; no upload, credentials or cache operations."""
import tkinter as tk
import logging
from tkinter import ttk
from collections import Counter

from .dialog_layout import DialogBody
from .message_label import MessageLabel

logger = logging.getLogger(__name__)


def skipped_messages(plan):
    counts = Counter(item.get("error_code", "OTHER") for item in plan.get("skipped_reports", []))
    for code, key in (("INVALID_REPORT", "invalid"), ("COMMANDER_MISMATCH", "commander_mismatches")):
        if plan.get(key):
            counts[code] += int(plan[key])
    missing = max(0, int(plan.get("skipped", 0)) - sum(counts.values()))
    if missing:
        counts["OTHER"] += missing
    remedies = {
        "STALE_UPDATE": "edit or re-mark in RhinoSpotter to retry.",
        "ACTIVE_TRANSITION_UNVERIFIABLE": "Active transition has no verifiable date; use Report Active only after checking the deposit.",
        "INVALID_REPORT": "correct the source data before syncing again.",
        "COMMANDER_MISMATCH": "select the matching Commander profile before syncing again.",
    }
    return [f"{count} Skipped — {remedies.get(code, 'source changes are required before syncing again.')}"
            for code, count in sorted(counts.items()) if count]


def show_edmc_sync_preview(parent, plan, *, palette=None, apply_theme=None,
                           position_window=None, button_factory=None, message_factory=None):
    from .sync_preview_dialog import confirmation_enabled, _usable_parent_bounds
    palette = palette or {}
    bg = palette.get("background", "#202020")
    fg = palette.get("foreground", "#f0f0f0")
    muted = palette.get("muted", fg)
    surface = palette.get("panel2", bg)
    line = palette.get("border", "#888888")
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title("Confirm Synchronization")
    layout = DialogBody(window, background=bg)
    outer = layout.content
    outer.columnconfigure(0, weight=1)
    result = False
    closed = False

    def close(confirmed=False):
        nonlocal result, closed
        if closed:
            return
        closed = True
        result = confirmed
        window.destroy()

    tk.Label(outer, text="Commander", bg=bg, fg=muted).grid(row=0, column=0, sticky="ew")
    MessageLabel(outer, text=str(plan.get("commander") or "(missing)"), bg=bg, fg=fg,
                 anchor="center", justify="center", font=(palette.get("font_family", "TkDefaultFont"), 12, "bold")).grid(
                     row=1, column=0, sticky="ew", pady=(1, 7))
    counts = tk.Frame(outer, bg=bg)
    counts.grid(row=2, column=0, sticky="ew")
    for index, (name, key) in enumerate((("New", "new"), ("Modified", "modified"), ("Unchanged", "unchanged"))):
        counts.columnconfigure(index, weight=1, uniform="counts")
        card = tk.Frame(counts, bg=surface, highlightbackground=line, highlightthickness=1,
                        padx=6, pady=1)
        card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 4, 0))
        card.columnconfigure(0, weight=1)
        tk.Label(card, text=str(int(plan.get(key, 0))), bg=surface, fg=fg,
                 font=(palette.get("font_family", "TkDefaultFont"), 13, "bold")).grid(row=0, column=0, sticky="ew")
        tk.Label(card, text=name, bg=surface, fg=muted,
                 font=(palette.get("font_family", "TkDefaultFont"), 9)).grid(row=1, column=0, sticky="ew")
    ready = int(plan.get("new", 0)) + int(plan.get("modified", 0))
    missing = int(plan.get("credential_missing", 0))
    messages = []
    if ready:
        messages.append(f"{ready} {'deposit' if ready == 1 else 'deposits'} ready to sync.")
    if missing:
        messages.append(f"{missing} {'deposit needs' if missing == 1 else 'deposits need'} API credentials before syncing.")
    messages.extend(skipped_messages(plan))
    if plan.get("confirm_blocked") and not plan.get("commander_mismatches"):
        messages.append("Synchronization is unavailable until the Commander is verified.")
    if not messages:
        messages.append("All deposits are up to date")
    for row, message in enumerate(messages, 3):
        MessageLabel(outer, text=message, bg=bg, fg=fg if row == 3 else muted,
                     anchor="center", justify="center").grid(row=row, column=0, sticky="ew", pady=(6, 0))
    factory = button_factory or ttk.Button
    cancel = factory(layout.footer, text="Cancel", command=close)
    cancel.pack(side="right", padx=(7, 0))
    confirm = factory(layout.footer, text="Confirm Sync", command=lambda: close(True))
    confirm.pack(side="right")
    if not confirmation_enabled(plan):
        confirm.configure(state=tk.DISABLED)
    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda event: close())
    try:
        if apply_theme:
            try:
                apply_theme(layout.outer)
            except Exception:
                logger.exception("Could not apply host theme to sync preview")
        layout.fit(parent, initial_width_dip=380, limit_to_parent=True)
        if _usable_parent_bounds(parent, window.winfo_screenwidth(), window.winfo_screenheight()):
            window.transient(parent.winfo_toplevel())
        if position_window:
            try:
                position_window(window)
            except Exception:
                logger.exception("Could not apply host positioning to sync preview")
        window.deiconify()
        window.grab_set()
        window.focus_force()
        parent.wait_window(window)
    finally:
        if window.winfo_exists():
            window.destroy()
    return result
