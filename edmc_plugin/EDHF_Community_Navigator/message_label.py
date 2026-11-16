"""Companion-owned message labels: wrap to allocated width, never size the host."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont


class MessageLabel(tk.Label):
    def __init__(self, master, **options):
        # A long message must not become the host's requested minimum width.
        # The initial wrap is font-relative; actual allocated width replaces it.
        options.pop("wraplength", None)
        options.setdefault("width", 1)
        options.setdefault("anchor", "w")
        options.setdefault("justify", "left")
        super().__init__(master, **options)
        self._hidden_layout = None
        self._wrap_width = None
        initial = tkfont.Font(font=self.cget("font")).measure("M" * 32)
        super().configure(wraplength=max(1, initial))
        self.bind("<Configure>", self._resize_message, add="+")

    def _resize_message(self, event):
        padding = sum(self.winfo_pixels(self.cget(key)) for key in ("padx", "borderwidth", "highlightthickness"))
        available = max(1, event.width - 2 * padding)
        if available != self._wrap_width:
            self._wrap_width = available
            # No geometry(), update(), idle loop or height-driven resize.
            super().configure(wraplength=available)

    def configure(self, cnf=None, **options):
        result = super().configure(cnf, **options)
        changed = dict(cnf) if isinstance(cnf, dict) else {}
        changed.update(options)
        if "text" in changed:
            if self.cget("text"):
                if self._hidden_layout:
                    manager, layout = self._hidden_layout
                    self._hidden_layout = None
                    if manager == "grid":
                        self.grid()
                    else:
                        self.pack(**layout)
            elif self.winfo_manager() == "grid":
                self._hidden_layout = ("grid", {})
                self.grid_remove()
            elif self.winfo_manager() == "pack":
                self._hidden_layout = ("pack", self.pack_info())
                self.pack_forget()
        return result

    config = configure


def sync_message(summary):
    """Presentation only: preserve outcome text, separate summary and causes."""
    from .batch_protocol import outcome_summary, sync_failure_text
    summary_text = outcome_summary(summary)
    details = sync_failure_text(summary)
    if not details:
        return summary_text
    # Separate each cause from its remedy without changing the underlying text
    # used by the sync service or other clients.
    lines = details.replace("; ", ". ").split(". ")
    formatted = "\n".join(line[:1].upper() + line[1:] + ("." if index < len(lines) - 1 else "")
                          for index, line in enumerate(lines))
    return summary_text + "\n" + formatted
