#!/usr/bin/env python3

"""v8 exact layout test generated from the user's layout.json model."""

import tkinter as tk
from tkinter import ttk

import finder_engine as legacy_engine
from hotspots_finder_gui_v8 import COLORS
from hotspots_finder_gui_v8_columnfilters import FILTER_COLUMNS
from hotspots_finder_gui_v8_community import COMMUNITY_FALLBACK_HEADERS
from hotspots_finder_gui_v8_expandresults import SORT_TABLES
from hotspots_finder_gui_v8_loglayout import FinderV8LogLayoutApp


WINDOW_WIDTH = 1359
WINDOW_HEIGHT = 819

# Exact boxes from layout.json.
BOXES = {
    "hotspots": (18, 92, 250, 130),
    "planets": (18, 227, 250, 130),
    "community": (18, 427, 250, 105),
    "systems": (285, 92, 225, 488),
    "faction": (18, 580, 225, 55),
    "power": (285, 615, 225, 55),
    "powerStates": (285, 680, 225, 75),
    "reference": (18, 640, 225, 55),
    "distance": (18, 700, 225, 55),
    "resultsPanel": (525, 92, 815, 650),
}

PANEL = COLORS["panel"]
ENTRY_BG = "#3b3b3b"
SCROLL_TRACK = "#17191b"
SCROLL_THUMB = "#454c53"
SCROLL_THUMB_ACTIVE = "#59636c"


class FinderV8PolishApp(FinderV8LogLayoutApp):
    def _configure_styles(self):
        super()._configure_styles()

        style = ttk.Style(self)

        # Thin, dark scrollbars with no bright native arrow buttons.
        style.configure(
            "Vertical.TScrollbar",
            background=SCROLL_THUMB,
            troughcolor=SCROLL_TRACK,
            bordercolor=SCROLL_TRACK,
            lightcolor=SCROLL_THUMB,
            darkcolor=SCROLL_THUMB,
            arrowcolor=SCROLL_TRACK,
            relief="flat",
            width=10,
            arrowsize=0,
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=SCROLL_THUMB,
            troughcolor=SCROLL_TRACK,
            bordercolor=SCROLL_TRACK,
            lightcolor=SCROLL_THUMB,
            darkcolor=SCROLL_THUMB,
            arrowcolor=SCROLL_TRACK,
            relief="flat",
            width=10,
            arrowsize=0,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", SCROLL_THUMB_ACTIVE)],
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[("active", SCROLL_THUMB_ACTIVE)],
        )

        # Under the clam theme these layouts remove the arrow elements
        # completely, leaving only a slim track + thumb.
        try:
            style.layout(
                "Vertical.TScrollbar",
                [
                    (
                        "Vertical.Scrollbar.trough",
                        {
                            "sticky": "ns",
                            "children": [
                                (
                                    "Vertical.Scrollbar.thumb",
                                    {"expand": "1", "sticky": "nswe"},
                                )
                            ],
                        },
                    )
                ],
            )
            style.layout(
                "Horizontal.TScrollbar",
                [
                    (
                        "Horizontal.Scrollbar.trough",
                        {
                            "sticky": "ew",
                            "children": [
                                (
                                    "Horizontal.Scrollbar.thumb",
                                    {"expand": "1", "sticky": "nswe"},
                                )
                            ],
                        },
                    )
                ],
            )
        except tk.TclError:
            pass

    def _build_ui(self):
        # State normally prepared by the intermediate feature-test layers.
        self.reference_system_var = tk.StringVar(master=self, value="")
        self.max_distance_var = tk.StringVar(master=self, value="50")
        self._distance_sort_state = {table: None for table in SORT_TABLES}
        self._body_sort_state = {table: None for table in SORT_TABLES}
        self._active_sort_column = {table: None for table in SORT_TABLES}

        self._column_filter_rows = {}
        self._column_filter_headers = {}
        self._column_filter_state = {
            table: {column: None for column in columns}
            for table, columns in FILTER_COLUMNS.items()
        }
        self._autosize_next_populate = set()

        self.community_deposits_enabled = tk.BooleanVar(master=self, value=False)
        self.community_commodity_filter = tk.StringVar(master=self, value="All")
        self.community_body_filter = tk.StringVar(master=self, value="All")
        self.community_all_headers = list(COMMUNITY_FALLBACK_HEADERS)
        self.community_all_rows = []
        self.rhino_upload_running = False

        # The model was made at this exact canvas size, so keep it exact.
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.resizable(False, False)

        self._stage = tk.Frame(self, bg=COLORS["bg"])
        self._stage.place(x=0, y=0, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)

        self._build_header()

        self._hotspots_box = self._make_box("hotspots")
        self._planets_box = self._make_box("planets")
        self._community_box = self._make_box("community")
        self._systems_panel = self._make_box("systems")
        self._faction_box = self._make_box("faction")
        self._power_box = self._make_box("power")
        self._power_states_box = self._make_box("powerStates")
        self._reference_box = self._make_box("reference")
        self._distance_box = self._make_box("distance")
        self._results_panel = self._make_box("resultsPanel")

        self._build_hotspots_box(self._hotspots_box)
        self._build_planets_box(self._planets_box)
        self._build_community_box(self._community_box)
        self._build_systems_box(self._systems_panel)
        self._build_system_filter_boxes()
        self._build_results(self._results_panel)
        self._build_bottom_bar()

        self.systems_text.bind("<<Paste>>", self._paste_systems_with_newline)

        # The in-app log uses classic tk.Scrollbar widgets; style those too.
        self._style_classic_scrollbars(self)

    def _build_header(self):
        header = tk.Frame(self._stage, bg="#242424")
        header.place(x=0, y=0, width=WINDOW_WIDTH, height=76)

        tk.Label(
            header,
            text="Hotspots & Landables Finder",
            bg="#242424",
            fg=COLORS["orange"],
            font=("Segoe UI", 18, "bold"),
        ).place(x=18, y=9)

        tk.Label(
            header,
            text="v8 local interface · Spansh · no Google Sheets",
            bg="#242424",
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        ).place(x=19, y=43)

    def _make_box(self, name):
        x, y, width, height = BOXES[name]
        box = tk.Frame(self._stage, bg=PANEL)
        box.place(x=x, y=y, width=width, height=height)
        return box

    @staticmethod
    def _section_label(parent, text, *, x=7, y=5):
        return tk.Label(
            parent,
            text=text,
            bg=PANEL,
            fg=COLORS["orange"],
            font=("Segoe UI", 9, "bold"),
        ).place(x=x, y=y)

    @staticmethod
    def _muted_label(parent, text, *, x, y, width=None):
        label = tk.Label(
            parent,
            text=text,
            bg=PANEL,
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        )
        if width is None:
            label.place(x=x, y=y)
        else:
            label.place(x=x, y=y, width=width)
        return label

    @staticmethod
    def _place_check(parent, text, variable, *, x, y, width, height=17, font=("Segoe UI", 8)):
        widget = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=PANEL,
            fg=COLORS["text"],
            activebackground=PANEL,
            activeforeground=COLORS["text"],
            selectcolor="#404040",
            highlightthickness=0,
            bd=0,
            padx=0,
            pady=0,
            anchor="w",
            font=font,
        )
        widget.place(x=x, y=y, width=width, height=height)
        return widget

    def _build_hotspots_box(self, parent):
        self._section_label(parent, "HOTSPOTS")
        self._place_check(
            parent, "Enable Hotspots", self.hotspots_enabled,
            x=7, y=24, width=112, height=18, font=("Segoe UI", 8)
        )
        self._place_check(
            parent, "Only Pristine", self.only_pristine,
            x=128, y=24, width=112, height=18, font=("Segoe UI", 8)
        )

        self._muted_label(parent, "Ring types", x=7, y=44)
        self._muted_label(parent, "Commodities", x=128, y=44)

        for row, (key, label) in enumerate((
            ("icy", "Icy"),
            ("metallic", "Metallic"),
            ("metal rich", "Metal Rich"),
            ("rocky", "Rocky"),
        )):
            self._place_check(
                parent, label, self.ring_vars[key],
                x=7, y=60 + row * 16, width=110, height=16
            )

        for row, (key, label) in enumerate((
            ("platinum", "Platinum"),
            ("bromellite", "Bromellite"),
            ("monazite", "Monazite"),
        )):
            self._place_check(
                parent, label, self.material_vars[key],
                x=128, y=60 + row * 16, width=112, height=16
            )

    def _build_planets_box(self, parent):
        self._section_label(parent, "PLANETS")
        self._place_check(
            parent, "Enable Planets", self.planets_enabled,
            x=7, y=24, width=112, height=18
        )
        self._place_check(
            parent, "Only Landables", self.only_landables,
            x=128, y=24, width=112, height=18
        )

        self._muted_label(parent, "Planet types", x=7, y=45)

        left = (
            ("metal rich", "Metal Rich"),
            ("high metal content", "HMC"),
            ("rocky", "Rocky"),
        )
        right = (
            ("rocky ice", "Rocky Ice"),
            ("icy", "Icy"),
        )

        for row, (key, label) in enumerate(left):
            self._place_check(
                parent, label, self.planet_type_vars[key],
                x=7, y=62 + row * 19, width=118, height=18
            )

        for row, (key, label) in enumerate(right):
            self._place_check(
                parent, label, self.planet_type_vars[key],
                x=128, y=62 + row * 19, width=112, height=18
            )

    def _build_community_box(self, parent):
        self._section_label(parent, "Alliance Community Deposits")
        self._place_check(
            parent,
            "Enable Community Deposits",
            self.community_deposits_enabled,
            x=7,
            y=27,
            width=190,
            height=20,
            font=("Segoe UI", 9),
        )

        self.rhino_upload_button = tk.Button(
            parent,
            text="Upload RhinoSpotter",
            command=self.start_rhino_upload,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            disabledforeground="#777777",
            relief="flat",
            padx=8,
            pady=2,
            font=("Segoe UI", 9),
        )
        self.rhino_upload_button.place(x=7, y=58, width=170, height=30)

    def _build_systems_box(self, parent):
        tk.Label(
            parent,
            text="SYSTEM INPUT",
            bg=PANEL,
            fg=COLORS["orange"],
            font=("Segoe UI", 10, "bold"),
        ).place(x=9, y=8)

        tk.Label(
            parent,
            textvariable=self.system_count_var,
            bg=PANEL,
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).place(x=9, y=29)

        text_frame = tk.Frame(parent, bg=PANEL)
        text_frame.place(x=9, y=52, width=207, height=300)

        self.systems_text = tk.Text(
            text_frame,
            bg="#242424",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            wrap="none",
            font=("Consolas", 10),
            undo=True,
            bd=0,
            highlightthickness=0,
        )
        scroll_y = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.systems_text.yview,
        )
        scroll_x = ttk.Scrollbar(
            text_frame,
            orient="horizontal",
            command=self.systems_text.xview,
            style="Horizontal.TScrollbar",
        )
        self.systems_text.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.systems_text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.rowconfigure(1, weight=0, minsize=9)
        text_frame.columnconfigure(0, weight=1)

        self.systems_text.bind(
            "<KeyRelease>",
            lambda _e: self._refresh_system_count(),
        )

        tk.Label(
            parent,
            text=(
                "Set input and filters to find matches.\n"
                "Leave empty to find matches using System Filters."
            ),
            bg=PANEL,
            fg=COLORS["muted"],
            justify="left",
            anchor="nw",
            wraplength=205,
            font=("Segoe UI", 8),
        ).place(x=9, y=361, width=207, height=55)

    def _build_system_filter_boxes(self):
        self._build_labeled_entry(
            self._faction_box,
            "Faction",
            self.faction_var,
        )

        self._build_labeled_entry(
            self._reference_box,
            "Reference system",
            self.reference_system_var,
        )

        self._build_labeled_entry(
            self._distance_box,
            "Max distance (LY)",
            self.max_distance_var,
        )

        self._muted_label(self._power_box, "Power", x=4, y=3)
        ttk.Combobox(
            self._power_box,
            textvariable=self.power_var,
            values=[""] + list(legacy_engine.POWER_LIST),
            state="readonly",
        ).place(x=4, y=22, width=217, height=27)

        self._muted_label(self._power_states_box, "Power states", x=4, y=3)
        states = (
            ("Unoccupied", 4, 23),
            ("Fortified", 113, 23),
            ("Exploited", 4, 47),
            ("Stronghold", 113, 47),
        )
        for state, x, y in states:
            self._place_check(
                self._power_states_box,
                state,
                self.power_state_vars[state],
                x=x,
                y=y,
                width=108,
                height=18,
                font=("Segoe UI", 8),
            )

    def _build_labeled_entry(self, parent, label, variable):
        self._muted_label(parent, label, x=4, y=3)
        tk.Entry(
            parent,
            textvariable=variable,
            bg=ENTRY_BG,
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
        ).place(x=4, y=22, width=217, height=27)

    @classmethod
    def _style_classic_scrollbars(cls, parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Scrollbar):
                try:
                    child.configure(
                        bg=SCROLL_THUMB,
                        activebackground=SCROLL_THUMB_ACTIVE,
                        troughcolor=SCROLL_TRACK,
                        relief="flat",
                        bd=0,
                        highlightthickness=0,
                        width=10,
                    )
                except tk.TclError:
                    pass
            cls._style_classic_scrollbars(child)

    def _toggle_results_expansion(self):
        if not self._results_expanded:
            self._log_was_visible_before_results_expand = self._log_visible
            if self._log_visible:
                self._log_panel.place_forget()

            # Hide every model box except Results.
            for name in (
                "_hotspots_box",
                "_planets_box",
                "_community_box",
                "_systems_panel",
                "_faction_box",
                "_power_box",
                "_power_states_box",
                "_reference_box",
                "_distance_box",
            ):
                getattr(self, name).place_forget()

            self._results_panel.place(
                x=18,
                y=92,
                width=1322,
                height=650,
            )

            if getattr(self, "_bottom_bar", None) is not None:
                self._bottom_bar.pack_forget()

            self._results_expanded = True
            self.expand_results_button.configure(text="Restore Panels")
            return

        # Restore exact model positions.
        mapping = {
            "_hotspots_box": "hotspots",
            "_planets_box": "planets",
            "_community_box": "community",
            "_systems_panel": "systems",
            "_faction_box": "faction",
            "_power_box": "power",
            "_power_states_box": "powerStates",
            "_reference_box": "reference",
            "_distance_box": "distance",
        }
        for attr, box_name in mapping.items():
            x, y, width, height = BOXES[box_name]
            getattr(self, attr).place(
                x=x,
                y=y,
                width=width,
                height=height,
            )

        x, y, width, height = BOXES["resultsPanel"]
        self._results_panel.place(
            x=x,
            y=y,
            width=width,
            height=height,
        )

        if getattr(self, "_bottom_bar", None) is not None:
            self._bottom_bar.pack(fill="x", side="bottom")

        self._results_expanded = False
        self.expand_results_button.configure(text="Expand Results")

        if self._log_was_visible_before_results_expand:
            self._log_visible = False
            self.after_idle(self._show_log_panel)


def main():
    app = FinderV8PolishApp()
    app.mainloop()


if __name__ == "__main__":
    main()
