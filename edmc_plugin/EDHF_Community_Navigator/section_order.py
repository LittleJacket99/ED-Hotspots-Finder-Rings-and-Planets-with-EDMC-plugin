"""Guarded EDMC plugin-panel ordering; no reparenting or plugin internals."""
import re
import tkinter as tk

POSITION_KEY = "edhf_community_companion_panel_position"
_PANEL = re.compile(r"plugin_(\d+)\Z")


class SectionOrder:
    def __init__(self, frame, config, *, is_busy=lambda: False):
        self.frame, self.config, self.is_busy = frame, config, is_busy
        self.panel = frame.master if _PANEL.fullmatch(frame.master.winfo_name()) else None
        self.box = self.panel.master if self.panel is not None else None
        self.up = self.down = None
        self._timer = None
        self._restored = False
        self._closed = False

    def attach(self, up, down):
        self.up, self.down = up, down
        self.refresh()
        self._timer = self.frame.after(100, self._restore, 50)

    def _slots(self):
        if self.panel is None or self.box is None:
            return []
        slots = []
        for widget in self.box.winfo_children():
            match = _PANEL.fullmatch(widget.winfo_name())
            if not match or widget.winfo_manager() != "grid":
                continue
            info = widget.grid_info()
            separator = self.box.children.get(f"plugin_hr_{match[1]}")
            if separator is None or separator.winfo_manager() != "grid":
                return []
            sep = separator.grid_info()
            row = int(info["row"])
            if (row < 1 or int(sep["row"]) != row - 1
                    or any(int(i.get("rowspan", 1)) != 1 or int(i.get("column", 0)) != 0
                           or int(i.get("columnspan", 1)) != 2 for i in (info, sep))
                    or set(self.box.grid_slaves(row=row)) != {widget}
                    or set(self.box.grid_slaves(row=row - 1)) != {separator}):
                return []
            slots.append((row, widget, separator))
        slots.sort(key=lambda item: item[0])
        if self.panel not in [item[1] for item in slots]:
            return []
        return slots

    def refresh(self):
        if self._closed:
            return
        try:
            slots = self._slots()
            index = next((i for i, slot in enumerate(slots) if slot[1] is self.panel), -1)
            idle = not self.is_busy()
            for button, neighbor in ((self.up, index - 1), (self.down, index + 1)):
                allowed = (idle and index >= 0 and 0 <= neighbor < len(slots)
                           and abs(slots[index][0] - slots[neighbor][0]) == 2)
                if button is not None:
                    button.configure(state=tk.NORMAL if allowed else tk.DISABLED)
        except tk.TclError:
            pass

    def move(self, step, *, persist=True):
        if self._closed or step not in (-1, 1) or self.is_busy():
            return False
        slots = self._slots()
        index = next((i for i, slot in enumerate(slots) if slot[1] is self.panel), -1)
        target = index + step
        if index < 0 or not 0 <= target < len(slots):
            self.refresh()
            return False
        first, second = slots[index], slots[target]
        if abs(first[0] - second[0]) != 2:
            self.refresh()
            return False
        # Change only geometry of complete host-owned wrapper/separator pairs.
        # Keep every other grid option and all descendants/bindings untouched.
        try:
            for (_, panel, separator), row in ((first, second[0]), (second, first[0])):
                panel.grid_configure(row=row)
                separator.grid_configure(row=row - 1)
        except tk.TclError:
            for row, panel, separator in (first, second):
                try:
                    panel.grid_configure(row=row)
                    separator.grid_configure(row=row - 1)
                except tk.TclError:
                    pass
            return False
        if persist:
            self._restored = True
            self.save()
        self.refresh()
        return True

    def save(self):
        slots = self._slots()
        index = next((i for i, item in enumerate(slots) if item[1] is self.panel), -1)
        if index >= 0:
            self.config.set(POSITION_KEY, index)

    def _restore(self, tries):
        self._timer = None
        if self._closed:
            return
        self.refresh()
        # EDMC 6.1.2 creates this control after gridding all plugin panels.
        # Read-only readiness check; no monkey-patching or imports of host internals.
        ready = self.box is not None and "update_button" in self.box.children
        if not ready or self.is_busy():
            if tries > 0:
                self._timer = self.frame.after(100, self._restore, tries - 1)
            return  # Unknown host: manual movement only, no speculative restore.
        slots = self._slots()
        if not slots:
            return
        try:
            target = int(self.config.get_int(POSITION_KEY, default=-1))
        except (TypeError, ValueError):
            return
        self._restored = True
        if target < 0:
            return
        target = min(target, len(slots) - 1)
        index = next(i for i, item in enumerate(slots) if item[1] is self.panel)
        while index != target:
            step = 1 if target > index else -1
            if not self.move(step, persist=False):
                break
            index += step
        self.refresh()

    def close(self):
        if self._timer is not None:
            try:
                self.frame.after_cancel(self._timer)
            except tk.TclError:
                pass
            self._timer = None
        if self._restored:
            try:
                self.save()
            except tk.TclError:
                pass
        self._closed = True


def attach_tooltip(widget, text):
    """Small local tooltip; uses no undocumented EDMC tooltip dependency."""
    state = {"timer": None, "window": None}

    def hide(_event=None):
        if state["timer"] is not None:
            try:
                widget.after_cancel(state["timer"])
            except tk.TclError:
                pass
            state["timer"] = None
        if state["window"] is not None:
            try:
                state["window"].destroy()
            except tk.TclError:
                pass
            state["window"] = None

    def show():
        state["timer"] = None
        window = tk.Toplevel(widget)
        state["window"] = window
        window.overrideredirect(True)
        tk.Label(window, text=text, bg=widget.cget("background"), fg=widget.cget("foreground"),
                 padx=4, pady=2, relief="solid", borderwidth=1).pack()
        window.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height()}")

    def enter(_event):
        hide()
        state["timer"] = widget.after(500, show)

    widget.bind("<Enter>", enter, add="+")
    for event in ("<Leave>", "<ButtonPress>", "<Destroy>"):
        widget.bind(event, hide, add="+")
