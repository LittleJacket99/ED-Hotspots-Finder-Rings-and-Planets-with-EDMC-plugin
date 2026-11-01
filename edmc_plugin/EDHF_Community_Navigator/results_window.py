from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable

from theme import theme


COLUMNS = (
    "Body",
    "Location",
    "Material",
    "Rigs",
    "Amount",
    "Density",
    "Depleted at",
    "Latitude",
    "Longitude",
    "Reports",
    "Updated",
)

CENTERED_COLUMNS = {"Location", "Rigs", "Reports"}

MIN_COLUMN_WIDTH = 55
MAX_COLUMN_WIDTH = 420
CELL_PADDING = 20
ROW_HEIGHT = 25
HEADER_HEIGHT = 27
MAX_VISIBLE_ROWS = 10


def _first(record: dict[str, Any], *keys: str):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return ""


def _format_depleted_at(value: Any) -> str:
    if value in (None, ""):
        return "Active"

    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]

    if len(text) >= 19:
        return text[:19]
    return text


def theme_colours() -> dict[str, str]:
    current = getattr(theme, "current", {}) or {}

    background = current.get("background") or "#101410"
    foreground = current.get("foreground") or "#f2f5f2"
    active_background = current.get("activebackground") or foreground
    active_foreground = current.get("activeforeground") or background
    disabled = current.get("disabledforeground") or foreground
    highlight = current.get("highlight") or foreground

    return {
        "background": background,
        "foreground": foreground,
        "muted": disabled,
        "header_bg": background,
        "header_fg": foreground,
        "selected_bg": active_background,
        "selected_fg": active_foreground,
        "border": disabled,
        "highlight": highlight,
        "font_family": "Segoe UI",
    }


# Keep the old private name available for any companion-local imports.
_theme_colours = theme_colours


class DepositsWindow:
    def __init__(
        self,
        master: tk.Misc,
        *,
        system: str,
        records: list[dict[str, Any]],
        on_track: Callable[[dict[str, Any]], None],
    ):
        self.records = records
        self.on_track = on_track
        self.selected_index: int | None = 0 if records else None
        self.row_widgets: dict[int, list[tk.Label]] = {}
        self.colours = theme_colours()

        self.window = tk.Toplevel(master)
        self.window.title(f"Community Deposits — {system}")
        self.window.attributes("-topmost", True)
        self.window.configure(background=self.colours["background"])

        outer = tk.Frame(
            self.window,
            background=self.colours["background"],
            padx=10,
            pady=10,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            outer,
            text=f"Community Deposits — {system} ({len(records)})",
            background=self.colours["background"],
            foreground=self.colours["foreground"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        title.pack(fill=tk.X, pady=(0, 8))

        self._display_rows = [
            (
                str(_first(record, "body", "body_name", "planet_name")),
                str(_first(record, "location_index", "location")),
                str(_first(record, "commodity", "material")),
                str(_first(record, "rigs")),
                str(_first(record, "amount")),
                str(_first(record, "density")),
                _format_depleted_at(record.get("depleted_at")),
                str(_first(record, "latitude", "lat")),
                str(_first(record, "longitude", "lon", "lng")),
                str(_first(record, "report_count", "reports_count", "reports")),
                str(_first(record, "updated_at", "last_reported_at", "last_seen_at")),
            )
            for record in records
        ]

        self.column_widths = self._measure_columns()
        table_width = sum(self.column_widths.values()) + len(COLUMNS)
        visible_rows = min(max(len(records), 1), MAX_VISIBLE_ROWS)
        table_height = HEADER_HEIGHT + visible_rows * ROW_HEIGHT

        screen_width = self.window.winfo_screenwidth()
        initial_canvas_width = min(
            table_width,
            max(620, int(screen_width * 0.90) - 40),
        )

        table_shell = tk.Frame(
            outer,
            background=self.colours["border"],
            bd=0,
        )
        table_shell.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            table_shell,
            width=initial_canvas_width,
            height=table_height,
            background=self.colours["background"],
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll_y = ttk.Scrollbar(
            table_shell,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
        )
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.configure(
            yscrollcommand=scroll_y.set,
        )

        self.table = tk.Frame(
            self.canvas,
            background=self.colours["background"],
        )
        self.table_window = self.canvas.create_window(
            (0, 0),
            window=self.table,
            anchor="nw",
        )

        self._build_header()
        self._build_rows()

        self.table.bind("<Configure>", self._sync_scrollregion)

        buttons = tk.Frame(
            outer,
            background=self.colours["background"],
        )
        buttons.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            buttons,
            text="Start Tracking",
            command=self._track_selected,
        ).pack(side=tk.RIGHT)

        self._apply_selection()

        # Let Tk calculate the complete requested height including the button
        # row, then make that the initial/minimum height. This prevents the
        # controls from being clipped below the table.
        self.window.update_idletasks()
        self._size_window(table_width)

    def _measure_columns(self) -> dict[str, int]:
        font = tkfont.Font(family="Segoe UI", size=9)
        widths: dict[str, int] = {}

        for column_index, name in enumerate(COLUMNS):
            width = font.measure(name) + CELL_PADDING

            for row in self._display_rows:
                width = max(
                    width,
                    font.measure(row[column_index]) + CELL_PADDING,
                )

            widths[name] = max(
                MIN_COLUMN_WIDTH,
                min(width, MAX_COLUMN_WIDTH),
            )

        return widths

    def _build_header(self) -> None:
        for column_index, name in enumerate(COLUMNS):
            width = self.column_widths[name]
            anchor = "center" if name in CENTERED_COLUMNS else "w"

            label = tk.Label(
                self.table,
                text=name,
                background=self.colours["header_bg"],
                foreground=self.colours["header_fg"],
                font=("Segoe UI", 9, "bold"),
                anchor=anchor,
                padx=7,
                pady=4,
                bd=0,
            )
            label.grid(
                row=0,
                column=column_index,
                sticky="nsew",
                padx=(0, 1),
                pady=(0, 1),
            )
            self.table.grid_columnconfigure(
                column_index,
                minsize=width,
            )

    def _build_rows(self) -> None:
        for row_index, row in enumerate(self._display_rows):
            widgets: list[tk.Label] = []

            for column_index, value in enumerate(row):
                column = COLUMNS[column_index]
                anchor = "center" if column in CENTERED_COLUMNS else "w"

                label = tk.Label(
                    self.table,
                    text=value,
                    background=self.colours["background"],
                    foreground=self.colours["foreground"],
                    font=("Segoe UI", 9),
                    anchor=anchor,
                    padx=7,
                    pady=3,
                    bd=0,
                )
                label.grid(
                    row=row_index + 1,
                    column=column_index,
                    sticky="nsew",
                    padx=(0, 1),
                    pady=(0, 1),
                )

                label.bind(
                    "<Button-1>",
                    lambda _event, index=row_index: self._select(index),
                )
                label.bind(
                    "<Double-1>",
                    lambda _event, index=row_index: self._track_index(index),
                )
                widgets.append(label)

            self.row_widgets[row_index] = widgets

    def _select(self, index: int) -> None:
        self.selected_index = index
        self._apply_selection()

    def _apply_selection(self) -> None:
        for row_index, widgets in self.row_widgets.items():
            selected = row_index == self.selected_index

            if selected:
                background = self.colours["selected_bg"]
                foreground = self.colours["selected_fg"]
            else:
                background = self.colours["background"]
                foreground = self.colours["foreground"]

            for widget in widgets:
                widget.configure(
                    background=background,
                    foreground=foreground,
                )

    def _track_index(self, index: int) -> None:
        self._select(index)
        self._track_selected()

    def _track_selected(self) -> None:
        if self.selected_index is None:
            return

        if 0 <= self.selected_index < len(self.records):
            self.on_track(self.records[self.selected_index])

    def _sync_scrollregion(self, _event=None) -> None:
        self.canvas.configure(
            scrollregion=self.canvas.bbox("all"),
        )

    def _size_window(self, table_width: int) -> None:
        self.window.update_idletasks()

        screen_width = self.window.winfo_screenwidth()
        max_width = int(screen_width * 0.92)
        desired_width = min(table_width + 55, max_width)
        window_width = max(desired_width, 650)

        # outer.winfo_reqheight() includes title, the capped table canvas
        # and the bottom action row.
        required_height = self.window.winfo_reqheight()
        window_height = required_height + 8

        self.window.geometry(f"{window_width}x{window_height}")

        # The popup is fully auto-sized to its contents, so keep it fixed:
        # this disables maximize/full-screen style resizing and avoids layout
        # changes that could hide the action row.
        self.window.resizable(False, False)
        self.window.minsize(window_width, window_height)
        self.window.maxsize(window_width, window_height)
