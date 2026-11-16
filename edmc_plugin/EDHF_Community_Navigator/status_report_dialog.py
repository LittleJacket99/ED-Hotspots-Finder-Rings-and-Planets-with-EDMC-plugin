"""Explicit confirmation using the existing EDMC palette and dialog geometry."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .message_label import MessageLabel
from .dialog_layout import DialogBody


def show_status_confirmation(parent, record, state, *, palette, apply_theme=None):
    bg, fg = palette["background"], palette["foreground"]
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title("Confirm Status Report")
    window.configure(background=bg)
    window.resizable(False, False)
    result = False
    closing = False

    def close(confirmed=False):
        nonlocal result, closing
        if closing:
            return
        closing = True
        result = confirmed
        window.destroy()

    layout = DialogBody(window, background=bg)
    outer = layout.content
    material = record.get("commodity") or f"Deposit {record.get('id', '')}"
    location = record.get("location_index")
    label = f"{material} — Location {location}" if location is not None else str(material)
    body = record.get("body") or ""
    MessageLabel(outer, text=f"You're about to report {label}\n{body} as {state.title()}.",
                 bg=bg, fg=fg, font=(palette["font_family"], 10, "bold")).pack(fill=tk.X, pady=(0, 12))
    MessageLabel(outer, text="Your report will be recorded in the community database.",
                 bg=bg, fg=fg).pack(fill=tk.X, pady=(0, 16))
    buttons = layout.footer
    ttk.Button(buttons, text="Cancel", command=close).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Confirm Report", command=lambda: close(True)).pack(side=tk.RIGHT)
    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda _event: close())
    try:
        if apply_theme:
            apply_theme(layout.outer)
        layout.fit(parent)
        window.transient(parent.winfo_toplevel())
        window.deiconify()
        window.grab_set()
        parent.wait_window(window)
    finally:
        try:
            if window.winfo_exists():
                window.grab_release()
                window.destroy()
        except tk.TclError:
            pass
    return result
