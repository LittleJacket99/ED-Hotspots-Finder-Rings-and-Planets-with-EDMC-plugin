"""Companion dialogs with wrapped content and an always-visible action row."""
import tkinter as tk
from tkinter import ttk, font as tkfont

from .message_label import MessageLabel


class DialogBody:
    def __init__(self, window, *, background):
        self.window = window
        self.outer = tk.Frame(window, bg=background, padx=12, pady=12)
        self.outer.grid(row=0, column=0, sticky="nsew")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)
        self.outer.rowconfigure(0, weight=1)
        self.outer.columnconfigure(0, weight=1)
        self.viewport = tk.Frame(self.outer, bg=background)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        self.viewport.rowconfigure(0, weight=1)
        self.viewport.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.viewport, bg=background, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.bar = ttk.Scrollbar(self.viewport, orient="vertical", command=self.canvas.yview)
        self.bar.grid(row=0, column=1, sticky="ns")
        self.bar.grid_remove()
        self.content = tk.Frame(self.canvas, bg=background)
        self.item = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.footer = tk.Frame(self.outer, bg=background)
        self.footer.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.canvas.configure(yscrollcommand=self._scroll_state)
        self.canvas.bind("<Configure>", self._resize_content)
        self.content.bind("<Configure>", self._content_changed)
        window.bind("<Next>", lambda event: self._page(1), add="+")
        window.bind("<Prior>", lambda event: self._page(-1), add="+")

    def _page(self, direction):
        self.canvas.yview_scroll(direction, "pages")
        return "break"

    def _scroll_state(self, first, last):
        self.bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.bar.grid_remove()
        else:
            self.bar.grid()

    def _resize_content(self, event):
        self.canvas.itemconfigure(self.item, width=max(1, event.width))

    def _content_changed(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._descendants(child)

    def _prime_width(self, width):
        """Measure wrapped height before Windows maps the withdrawn dialog."""
        self.canvas.itemconfigure(self.item, width=width)
        for label in self._descendants(self.content):
            if not isinstance(label, MessageLabel):
                continue
            available = width
            ancestor = label.master
            while ancestor is not self.content:
                if "padx" in ancestor.keys():
                    available -= 2 * ancestor.winfo_pixels(ancestor.cget("padx"))
                ancestor = ancestor.master
            layout = label.grid_info() or label.pack_info()
            padx = layout.get("padx", 0)
            values = label.tk.splitlist(str(padx))
            available -= sum(label.winfo_pixels(v) for v in values) * (2 if len(values) == 1 else 1)
            label._resize_message(type("Size", (), {"width": max(1, available)})())
        self.window.update_idletasks()

    def fit(self, parent, *, initial_width_dip=None, limit_to_parent=False):
        from .sync_preview_dialog import _centered_geometry, _usable_parent_bounds
        self.window.update_idletasks()
        font = tkfont.nametofont("TkDefaultFont")
        messages = [w for w in self._descendants(self.content) if isinstance(w, MessageLabel)]
        preferred = max((tkfont.Font(font=w.cget("font")).measure("M" * 36) for w in messages),
                        default=font.measure("M" * 36))
        screen_w, screen_h = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        if initial_width_dip is not None:
            # Initial preference only, not a fixed/minimum window size. Tk's
            # effective DPI follows its current scaling (points -> pixels).
            preferred = round(initial_width_dip * self.window.winfo_fpixels("1i") / 96)
            bounds = _usable_parent_bounds(parent, screen_w, screen_h)
            if limit_to_parent and bounds:
                preferred = min(preferred, bounds[2])
        # Reserve space for native title bar/borders using scaled font metrics.
        max_w = max(1, screen_w - font.metrics("linespace") * 2)
        max_h = max(1, screen_h - font.metrics("linespace") * 5)
        width = min(max(preferred, self.footer.winfo_reqwidth() + 24,
                        self.content.winfo_reqwidth() + 24), max_w)
        footer_h = self.footer.winfo_reqheight() + 12
        content_w = max(1, width - 24)
        self._prime_width(content_w)
        available_h = max(1, max_h - footer_h - 24)
        if self.content.winfo_reqheight() > available_h:
            self.bar.grid()
            content_w = max(1, content_w - self.bar.winfo_reqwidth())
            self._prime_width(content_w)
        natural_h = self.content.winfo_reqheight()
        self.canvas.configure(width=content_w, height=min(natural_h, available_h))
        self.canvas.configure(scrollregion=(0, 0, content_w, natural_h))
        height = min(natural_h + footer_h + 24, max_h)
        self.window.geometry(_centered_geometry(parent, width, height, screen_w, screen_h))
        self.window.resizable(True, True)
        self.window.minsize(min(width, self.footer.winfo_reqwidth() + 24),
                            min(height, footer_h + 24 + font.metrics("linespace") * 2))
        for widget in (self.canvas, self.content, *self._descendants(self.content)):
            widget.bind("<MouseWheel>", self._wheel, add="+")
        self.window.update_idletasks()

    def _wheel(self, event):
        if self.bar.winfo_manager():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"
