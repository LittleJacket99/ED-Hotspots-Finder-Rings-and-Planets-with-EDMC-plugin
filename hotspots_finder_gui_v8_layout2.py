#!/usr/bin/env python3

"""v8 layout based on the user's latest wireframe."""

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from urllib.parse import quote_plus

import system_filter_search
from hotspots_finder_gui_v8 import APP_TITLE, COLORS
from hotspots_finder_gui_v8_polish import FinderV8PolishApp as BasePolishApp


LAYOUT = {
    "_hotspots_box": (18, 92, 250, 130),
    "_planets_box": (18, 232, 250, 130),
    "_community_box": (18, 372, 250, 195),
    "_systems_panel": (285, 92, 225, 420),
    "_faction_box": (18, 620, 237, 55),
    "_power_box": (285, 620, 225, 55),
    "_power_states_box": (285, 680, 225, 70),
    "_reference_box": (18, 680, 142, 55),
    "_distance_box": (165, 680, 90, 55),
    "_results_panel": (525, 92, 815, 650),
}

CLEAR_BUTTON_Y = 520
CLEAR_BUTTON_WIDTH = 109
CLEAR_BUTTON_HEIGHT = 27
CLEAR_BUTTON_GAP = 7
WINDOW_TOP_MARGIN = 10
WINDOW_WIDTH = 1359
WINDOW_HEIGHT = 819
RESULTS_RIGHT_MARGIN = 19
RESULTS_BOTTOM_MARGIN = 77
EXPANDED_LEFT_MARGIN = 18
EXPANDED_BOTTOM_MARGIN = 19
RHINOSPOTTER_REPOSITORY_URL = "https://github.com/Fumlop/EDRhinoSpotter"
MINERALS_TABLE_URL = "https://docs.google.com/spreadsheets/d/1SVTKW-Uy6sjjR0oFqKjCI5tDvYAu97ORmocXwl1ckU0/edit?gid=0#gid=0"
VOLCANISM_TABLE_URL = "https://wiknow.pages.dev/ref/ground-mining"


class FinderV8Layout2App(BasePolishApp):
    def _configure_styles(self):
        """Keep the native scrollbar geometry available to the active layout."""

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        horizontal_layout = style.layout("Horizontal.TScrollbar")
        vertical_layout = style.layout("Vertical.TScrollbar")

        super()._configure_styles()

        try:
            style.layout("Horizontal.TScrollbar", horizontal_layout)
            style.layout("Vertical.TScrollbar", vertical_layout)
        except tk.TclError:
            pass

    def _build_ui(self):
        self._row_system_by_tree = {}
        self._context_tree = None
        self._context_iid = None
        self._responsive_layout_pending = False

        super()._build_ui()

        # Keep the normal window near the top of the desktop. The base size is
        # also the minimum supported size; larger windows are handled by the
        # responsive layout below instead of scaling fonts and controls.
        screen_width = self.winfo_screenwidth()
        x = max(10, (screen_width - WINDOW_WIDTH) // 2)
        self.geometry(f"+{x}+{WINDOW_TOP_MARGIN}")
        self.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.resizable(True, True)

        # The header is created by the base layout. Keep a reference so its
        # background can extend across the full width when the window grows.
        self._header_frame = None
        for child in self._stage.winfo_children():
            if not isinstance(child, tk.Frame):
                continue
            try:
                if str(child.cget("bg")) == "#242424":
                    self._header_frame = child
                    break
            except tk.TclError:
                continue

        for attr, (box_x, box_y, width, height) in LAYOUT.items():
            getattr(self, attr).place(x=box_x, y=box_y, width=width, height=height)

        self._reflow_systems_contents()
        self._reflow_compact_reference_distance()
        self._configure_power_combobox_behavior()
        self._configure_rhino_upload_help()
        self._build_external_clear_buttons()
        self._build_reference_tables_button()

        # Resize only the areas that benefit from extra room. The filters and
        # input controls keep their tested pixel geometry, while Results grows.
        self.bind("<Configure>", self._schedule_responsive_layout, add="+")
        self.after_idle(self._apply_responsive_layout)

    def _schedule_responsive_layout(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self._responsive_layout_pending:
            return
        self._responsive_layout_pending = True
        self.after_idle(self._apply_responsive_layout)

    def _apply_responsive_layout(self):
        self._responsive_layout_pending = False

        try:
            width = max(WINDOW_WIDTH, int(self.winfo_width()))
            height = max(WINDOW_HEIGHT, int(self.winfo_height()))
        except (TypeError, ValueError, tk.TclError):
            return

        # Extend the stage and title background to the current client area.
        try:
            self._stage.place_configure(width=width, height=height)
        except tk.TclError:
            pass
        if self._header_frame is not None:
            try:
                self._header_frame.place_configure(width=width)
            except tk.TclError:
                pass

        # Keep the two header actions anchored to the right edge.
        settings_button = getattr(self, "settings_button", None)
        if settings_button is not None:
            try:
                settings_button.place_configure(x=width - 114, y=20)
            except tk.TclError:
                pass

        reference_button = getattr(self, "reference_tables_button", None)
        if reference_button is not None:
            try:
                reference_button.place_configure(x=width - 294, y=20)
            except tk.TclError:
                pass

        if getattr(self, "_results_expanded", False):
            results_width = max(
                1,
                width - EXPANDED_LEFT_MARGIN - RESULTS_RIGHT_MARGIN,
            )
            results_height = max(
                1,
                height - LAYOUT["_results_panel"][1] - EXPANDED_BOTTOM_MARGIN,
            )
            self._results_panel.place(
                x=EXPANDED_LEFT_MARGIN,
                y=LAYOUT["_results_panel"][1],
                width=results_width,
                height=results_height,
            )
            return

        results_x, results_y, base_width, base_height = LAYOUT["_results_panel"]
        results_width = max(base_width, width - results_x - RESULTS_RIGHT_MARGIN)
        results_height = max(base_height, height - results_y - RESULTS_BOTTOM_MARGIN)
        self._results_panel.place(
            x=results_x,
            y=results_y,
            width=results_width,
            height=results_height,
        )

    def _build_reference_tables_button(self):
        """Add quick links to the external mining reference tables."""

        self.reference_tables_menu = tk.Menu(self, tearoff=False)
        self.reference_tables_menu.add_command(
            label="Minerals Table",
            command=lambda: webbrowser.open(MINERALS_TABLE_URL, new=2),
        )
        self.reference_tables_menu.add_command(
            label="Volcanism Table",
            command=lambda: webbrowser.open(VOLCANISM_TABLE_URL, new=2),
        )

        self.reference_tables_button = tk.Button(
            self._stage,
            text="Reference Tables ▾",
            command=self._show_reference_tables_menu,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=10,
            pady=3,
            font=("Segoe UI", 9),
        )
        # Align the right edge with the Results panel / Expand Results button.
        self.reference_tables_button.place(x=1170, y=20, width=170, height=30)

    def _show_reference_tables_menu(self):
        button = self.reference_tables_button
        try:
            self.reference_tables_menu.tk_popup(
                button.winfo_rootx(),
                button.winfo_rooty() + button.winfo_height(),
            )
        finally:
            self.reference_tables_menu.grab_release()

    def _configure_rhino_upload_help(self):
        """Make the Community Deposits actions obvious and self-explanatory."""

        self._rhino_help_popup = None
        self.rhino_upload_button.configure(text="Sync Deposits to Database")
        self.rhino_upload_button.place_configure(x=7, y=58, width=190, height=30)

        self.rhino_help_button = tk.Label(
            self._community_box,
            text="?",
            bg="#3a4148",
            fg=COLORS["text"],
            relief="solid",
            bd=1,
            font=("Segoe UI", 10, "bold"),
            cursor="question_arrow",
        )
        self.rhino_help_button.place(x=203, y=61, width=24, height=24)
        self.rhino_help_button.bind("<Enter>", self._show_rhino_upload_help)
        self.rhino_help_button.bind("<Leave>", self._hide_rhino_upload_help)

        self.get_rhinospotter_button = tk.Button(
            self._community_box,
            text="Get RhinoSpotter by Fumlop",
            command=self._open_rhinospotter_repository,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=8,
            pady=2,
            font=("Segoe UI", 9),
        )
        self.get_rhinospotter_button.place(x=7, y=104, width=190, height=30)

    @staticmethod
    def _open_rhinospotter_repository():
        webbrowser.open(RHINOSPOTTER_REPOSITORY_URL, new=2)

    def _show_rhino_upload_help(self, _event=None):
        if self._rhino_help_popup is not None:
            return

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass

        x = self.rhino_help_button.winfo_rootx() + self.rhino_help_button.winfo_width() + 8
        y = self.rhino_help_button.winfo_rooty() - 5
        popup.geometry(f"+{x}+{y}")

        tk.Label(
            popup,
            text=(
                "Reads deposit reports saved locally by RhinoSpotter and syncs "
                "them with the Community Deposits database. Matching reports "
                "are updated instead of being duplicated.\n\n"
                "Community Deposits are accessible only to authorized users "
                "through a valid API key, configurable in Settings."
            ),
            bg="#f4f4f4",
            fg="#111111",
            justify="left",
            anchor="w",
            wraplength=310,
            padx=9,
            pady=7,
            relief="solid",
            bd=1,
            font=("Segoe UI", 9),
        ).pack()

        self._rhino_help_popup = popup

    def _hide_rhino_upload_help(self, _event=None):
        popup = self._rhino_help_popup
        self._rhino_help_popup = None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

    def _make_tree(self, parent):
        """Create a result tree with a deliberately obvious test scrollbar."""

        frame = tk.Frame(parent, bg=COLORS["panel"])
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, show="headings", selectmode="extended")
        ybar = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=tree.yview,
            style="Vertical.TScrollbar",
        )

        # Use a classic Tk scrollbar temporarily. It is intentionally large
        # and light so functionality can be verified before final GUI styling.
        xbar = tk.Scrollbar(
            frame,
            orient="horizontal",
            command=tree.xview,
            bg="#e6e6e6",
            activebackground="#ffffff",
            troughcolor="#666666",
            relief="raised",
            bd=1,
            highlightthickness=0,
            width=18,
        )
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.rowconfigure(1, weight=0, minsize=20)
        frame.columnconfigure(0, weight=1)
        return tree

    def _build_results(self, parent):
        super()._build_results(parent)

        # Fourth result tab: generated system lists live here. The Systems box
        # remains manual input only and is never used as an output container.
        self.systems_result_tab = tk.Frame(self.notebook, bg=COLORS["panel"])
        self.notebook.add(self.systems_result_tab, text="Systems (0)")
        self.systems_result_tree = self._make_tree(self.systems_result_tab)

        self._build_result_context_menu()

    def _populate_tree(self, tree, headers, rows):
        """Populate results, retain row systems, and keep columns scrollable."""

        headers = list(headers or [])
        rows = list(rows or [])
        super()._populate_tree(tree, headers, rows)

        # Do not let Treeview stretch every column to the viewport. Fixed
        # minimum widths create real horizontal overflow when a result table
        # contains many columns, which makes xview/scrollbar actually usable.
        preferred_widths = {
            "System": 190,
            "Star system": 190,
            "Body": 180,
            "Ring": 170,
            "Commodity": 145,
            "Distance": 115,
            "Distance (LY)": 115,
            "Latitude": 115,
            "Longitude": 115,
        }
        for header in headers:
            current_width = int(tree.column(header, "width") or 0)
            preferred = preferred_widths.get(header, 135)
            tree.column(
                header,
                width=max(current_width, preferred),
                minwidth=70,
                stretch=False,
            )
            tree.heading(header, anchor="w")
        try:
            tree.xview_moveto(0)
        except tk.TclError:
            pass

        system_map = {}
        current_system = ""
        if "System" in headers:
            for iid, row in zip(tree.get_children(""), rows):
                value = ""
                if isinstance(row, dict):
                    value = str(row.get("System", "") or "").strip()
                if value:
                    current_system = value
                if current_system:
                    system_map[iid] = current_system

        self._row_system_by_tree[tree] = system_map

    def _configure_power_combobox_behavior(self):
        """Do not let mouse-wheel scrolling accidentally change the Power."""

        for child in self._power_box.winfo_children():
            if not isinstance(child, ttk.Combobox):
                continue

            self.power_combo = child
            child.bind("<MouseWheel>", self._block_power_mousewheel, add="+")
            child.bind(
                "<<ComboboxSelected>>",
                self._power_combobox_selected,
                add="+",
            )
            child.bind(
                "<FocusOut>",
                self._clear_power_combobox_selection,
                add="+",
            )
            break

    @staticmethod
    def _block_power_mousewheel(_event=None):
        return "break"

    def _power_combobox_selected(self, _event=None):
        # Remove focus and the Entry-style text selection left by ttk on
        # Windows after choosing a readonly combobox item.
        self.after_idle(self._clear_power_combobox_selection)

    def _clear_power_combobox_selection(self, _event=None):
        combo = getattr(self, "power_combo", None)
        if combo is None:
            return

        try:
            if self.focus_get() is combo:
                self.focus_set()
            combo.selection_clear()
            combo.icursor("end")
        except tk.TclError:
            pass

    def _build_result_context_menu(self):
        # Menu entries are rebuilt for every right-click so website actions can
        # disappear entirely for a multi-row selection.
        self._result_context_menu = tk.Menu(self, tearoff=False)

        for tree in (
            self.hotspot_tree,
            self.planet_tree,
            self.community_tree,
            self.systems_result_tree,
        ):
            tree.bind(
                "<Button-3>",
                self._show_result_context_menu,
                add="+",
            )
            tree.bind(
                "<Control-c>",
                self._copy_selected_rows_shortcut,
                add="+",
            )

    def _show_result_context_menu(self, event):
        tree = event.widget
        iid = tree.identify_row(event.y)
        if not iid:
            return "break"

        # Right-clicking one of several already-selected rows must preserve the
        # multi-selection. Right-clicking elsewhere starts a new selection.
        if iid not in tree.selection():
            tree.selection_set(iid)
        tree.focus(iid)
        self._context_tree = tree
        self._context_iid = iid

        selected_iids = self._selected_context_iids()
        selected_systems = self._selected_context_systems()
        row_count = len(selected_iids)
        system_count = len(selected_systems)

        menu = self._result_context_menu
        menu.delete(0, "end")
        menu.add_command(
            label="Copy row" if row_count == 1 else f"Copy {row_count} rows",
            command=self._copy_context_row,
            state="normal" if row_count else "disabled",
        )
        menu.add_command(
            label=(
                "Copy system"
                if system_count <= 1
                else f"Copy {system_count} systems"
            ),
            command=self._copy_context_system,
            state="normal" if system_count else "disabled",
        )

        # Website actions are shown only for exactly one selected row. This
        # removes any ambiguity when Shift/Ctrl selection is active.
        if row_count == 1 and system_count == 1:
            menu.add_separator()
            menu.add_command(
                label="Open system in Inara",
                command=lambda: self._open_context_system("inara"),
            )
            menu.add_command(
                label="Open system in Spansh",
                command=lambda: self._open_context_system("spansh"),
            )
            menu.add_command(
                label="Open system in EDSM",
                command=lambda: self._open_context_system("edsm"),
            )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _selected_context_iids(self):
        tree = self._context_tree
        if tree is None:
            return []

        selected = set(tree.selection())
        if not selected and self._context_iid:
            selected.add(self._context_iid)

        # Treeview.selection() order is not guaranteed. Copy rows in the same
        # top-to-bottom order currently visible to the user.
        return [iid for iid in tree.get_children("") if iid in selected]

    def _system_for_iid(self, tree, iid):
        if tree is None or not iid:
            return ""

        mapped = self._row_system_by_tree.get(tree, {}).get(iid, "")
        if mapped:
            return str(mapped).strip()

        columns = list(tree["columns"])
        if "System" in columns:
            return str(tree.set(iid, "System") or "").strip()
        return ""

    def _selected_context_systems(self):
        tree = self._context_tree
        systems = []
        seen = set()
        for iid in self._selected_context_iids():
            system = self._system_for_iid(tree, iid)
            key = system.casefold()
            if not system or key in seen:
                continue
            seen.add(key)
            systems.append(system)
        return systems

    def _context_system(self):
        return self._system_for_iid(self._context_tree, self._context_iid)

    def _copy_text(self, text, status):
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set(status)

    def _copy_context_row(self):
        tree = self._context_tree
        if tree is None:
            return

        iids = self._selected_context_iids()
        if not iids:
            return

        columns = list(tree["columns"])
        lines = []
        for iid in iids:
            values = [str(tree.set(iid, column) or "") for column in columns]

            # If compact display blanked the repeated System cell, copy the
            # actual system name so every copied row is self-contained.
            if "System" in columns:
                index = columns.index("System")
                if not values[index].strip():
                    values[index] = self._system_for_iid(tree, iid)

            lines.append("\t".join(values))

        count = len(lines)
        status = "Row copied" if count == 1 else f"{count} rows copied"
        self._copy_text("\n".join(lines), status)

    def _copy_context_system(self):
        systems = self._selected_context_systems()
        if not systems:
            return

        count = len(systems)
        status = (
            f"Copied system: {systems[0]}"
            if count == 1
            else f"{count} systems copied"
        )
        self._copy_text("\n".join(systems), status)

    def _copy_selected_rows_shortcut(self, event):
        tree = event.widget
        selected = list(tree.selection())
        if not selected:
            return "break"

        self._context_tree = tree
        focused = tree.focus()
        self._context_iid = focused if focused in selected else selected[0]
        self._copy_context_row()
        return "break"

    def _open_context_system(self, target):
        if len(self._selected_context_iids()) != 1:
            return

        systems = self._selected_context_systems()
        if len(systems) != 1:
            return
        system = systems[0]

        if target == "inara":
            url = (
                "https://inara.cz/elite/starsystem/?search="
                + quote_plus(system)
            )
            self._open_system_url(url, system, "Inara")
            return

        if target == "edsm":
            url = (
                "https://www.edsm.net/en/system?systemName="
                + quote_plus(system)
            )
            self._open_system_url(url, system, "EDSM")
            return

        if target == "spansh":
            self.status_var.set(f'Resolving {system} on Spansh...')
            threading.Thread(
                target=self._open_spansh_system_worker,
                args=(system,),
                daemon=True,
            ).start()

    def _open_spansh_system_worker(self, system):
        try:
            record = system_filter_search._lookup_system_record(system)
            id64 = record.get("id64")
            if id64 in (None, ""):
                raise ValueError(
                    f'Spansh did not return an ID64 for "{system}".'
                )
            url = f"https://spansh.co.uk/system/{id64}"
            self.after(0, self._open_system_url, url, system, "Spansh")
        except Exception as exc:
            message = str(exc)
            self.after(0, self._open_system_link_failed, message)

    def _open_system_url(self, url, system, service):
        webbrowser.open(url, new=2)
        self.status_var.set(f"Opened {system} in {service}")

    def _open_system_link_failed(self, message):
        self.status_var.set("Unable to open system link")
        messagebox.showerror(APP_TITLE, message, parent=self)

    def start_scan(self):
        """Start the unified SCAN flow with the new system-resolution rules."""
        if self.running:
            return

        config = self._collect_config()
        has_system_selector = bool(
            config.get("systems")
            or config.get("faction_name")
            or config.get("power_name")
            or config.get("reference_system")
        )
        hp_enabled = bool(
            config.get("hotspots_enabled") or config.get("planets_enabled")
        )
        community_enabled = bool(config.get("community_deposits_enabled"))

        if hp_enabled and not has_system_selector:
            messagebox.showwarning(
                APP_TITLE,
                "Hotspots/Planets require manual systems or a System Filter.",
                parent=self,
            )
            return

        if not hp_enabled and not community_enabled and not has_system_selector:
            messagebox.showwarning(
                APP_TITLE,
                "Add at least one manual system or set a System Filter.",
                parent=self,
            )
            return

        self.running = True
        self.cancel_event.clear()
        self.scan_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.rhino_upload_button.configure(state="disabled")
        self.progress.start(12)
        self.status_var.set("Scanning...")

        threading.Thread(
            target=self._scan_worker,
            args=(config,),
            daemon=True,
        ).start()

    def _finish_scan(self, status):
        super()._finish_scan(status)
        if not self.rhino_upload_running:
            self.rhino_upload_button.configure(state="normal")

    def _scan_complete(self, result):
        super()._scan_complete(result)

        headers = list(result.get("system_headers", ["System"]) or ["System"])
        rows = list(result.get("system_rows", []) or [])
        self._populate_tree(self.systems_result_tree, headers, rows)
        self.notebook.tab(
            self.systems_result_tab,
            text=f"Systems ({len(rows)})",
        )

        # The Systems tab is deliberately a simple result table: direct clicks
        # sort System or Distance without adding another filter layer.
        for header in headers:
            self.systems_result_tree.heading(
                header,
                text=header,
                command=lambda h=header: self._sort_tree(
                    self.systems_result_tree,
                    h,
                    False,
                ),
            )

        if result.get("status") == "SYSTEM_LIST_READY":
            self.notebook.select(self.systems_result_tab)

    def _current_export_source(self):
        if self.notebook.select() == str(self.systems_result_tab):
            return "Systems", self.systems_result_tree
        return super()._current_export_source()

    def _reflow_systems_contents(self):
        """Fit manual Systems input inside the box, leaving Clear buttons outside."""
        for child in self._systems_panel.winfo_children():
            if isinstance(child, tk.Frame):
                child.place_configure(x=9, y=52, width=207, height=300)
                continue

            if isinstance(child, tk.Button):
                child.place_forget()
                continue

            if isinstance(child, tk.Label):
                text = str(child.cget("text") or "")
                if text.startswith("Optional manual input"):
                    child.place_configure(x=9, y=361, width=207, height=50)

    def _reflow_compact_reference_distance(self):
        """Fit Faction, Reference and Max Distance into layout (7) boxes."""
        for child in self._faction_box.winfo_children():
            if isinstance(child, tk.Entry):
                child.place_configure(x=4, y=22, width=229, height=27)

        for child in self._reference_box.winfo_children():
            if isinstance(child, tk.Entry):
                child.place_configure(x=4, y=22, width=134, height=27)

        for child in self._distance_box.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(text="Max LY")
                child.place_configure(x=4, y=3, width=82)
            elif isinstance(child, tk.Entry):
                child.place_configure(x=4, y=22, width=82, height=27)

    def _build_external_clear_buttons(self):
        x = LAYOUT["_systems_panel"][0]
        right_x = x + CLEAR_BUTTON_WIDTH + CLEAR_BUTTON_GAP

        self._external_clear_filters_button = tk.Button(
            self._stage,
            text="Clear Filters",
            command=self._clear_scan_filters,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
        )
        self._external_clear_filters_button.place(
            x=x,
            y=CLEAR_BUTTON_Y,
            width=CLEAR_BUTTON_WIDTH,
            height=CLEAR_BUTTON_HEIGHT,
        )

        self._external_clear_systems_button = tk.Button(
            self._stage,
            text="Clear Systems",
            command=self._clear_systems,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
        )
        self._external_clear_systems_button.place(
            x=right_x,
            y=CLEAR_BUTTON_Y,
            width=CLEAR_BUTTON_WIDTH,
            height=CLEAR_BUTTON_HEIGHT,
        )

    def _hide_external_clear_buttons(self):
        self._external_clear_systems_button.place_forget()
        self._external_clear_filters_button.place_forget()

    def _show_external_clear_buttons(self):
        x = LAYOUT["_systems_panel"][0]
        right_x = x + CLEAR_BUTTON_WIDTH + CLEAR_BUTTON_GAP

        self._external_clear_filters_button.place(
            x=x,
            y=CLEAR_BUTTON_Y,
            width=CLEAR_BUTTON_WIDTH,
            height=CLEAR_BUTTON_HEIGHT,
        )
        self._external_clear_systems_button.place(
            x=right_x,
            y=CLEAR_BUTTON_Y,
            width=CLEAR_BUTTON_WIDTH,
            height=CLEAR_BUTTON_HEIGHT,
        )

    def _toggle_results_expansion(self):
        if not self._results_expanded:
            self._log_was_visible_before_results_expand = self._log_visible
            if self._log_visible:
                self._log_panel.place_forget()

            for attr in (
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
                getattr(self, attr).place_forget()

            self._hide_external_clear_buttons()

            if getattr(self, "_bottom_bar", None) is not None:
                self._bottom_bar.pack_forget()

            self._results_expanded = True
            self.expand_results_button.configure(text="Restore Panels")
            self._apply_responsive_layout()
            return

        for attr, (box_x, box_y, width, height) in LAYOUT.items():
            getattr(self, attr).place(x=box_x, y=box_y, width=width, height=height)

        self._reflow_systems_contents()
        self._reflow_compact_reference_distance()
        self._show_external_clear_buttons()

        if getattr(self, "_bottom_bar", None) is not None:
            self._bottom_bar.pack(fill="x", side="bottom")

        self._results_expanded = False
        self.expand_results_button.configure(text="Expand Results")
        self._apply_responsive_layout()

        if self._log_was_visible_before_results_expand:
            self._log_visible = False
            self.after_idle(self._show_log_panel)


def main():
    app = FinderV8Layout2App()
    app.mainloop()


if __name__ == "__main__":
    main()
