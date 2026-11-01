#!/usr/bin/env python3

"""v8 feature test: expand/collapse panels to maximize results."""

from collections import deque
from datetime import datetime
import sys
import threading
import tkinter as tk
from tkinter import ttk

from hotspots_finder_gui_v8 import COLORS
from hotspots_finder_gui_v8_columnfilters import FinderV8ColumnFiltersApp


DISTANCE_COLUMN = "Distance (LY)"
BODY_COLUMN = "Body"
SORT_TABLES = ("hotspots", "planets", "community")


class _LogCapture:
    """Tee stdout/stderr into the GUI log while preserving the console."""

    def __init__(self, app, channel, original):
        self.app = app
        self.channel = channel
        self.original = original
        self.encoding = getattr(original, "encoding", "utf-8") or "utf-8"

    def write(self, text):
        if self.original is not None:
            try:
                self.original.write(text)
            except Exception:
                pass
        self.app._capture_log_text(self.channel, text)
        return len(text or "")

    def flush(self):
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self):
        if self.original is None:
            return False
        try:
            return self.original.isatty()
        except Exception:
            return False

    def fileno(self):
        if self.original is None:
            raise OSError("No console file descriptor")
        return self.original.fileno()


class FinderV8ExpandResultsApp(FinderV8ColumnFiltersApp):
    def __init__(self):
        self._log_lock = threading.Lock()
        self._log_lines = deque(maxlen=1000)
        self._log_partial = {"stdout": "", "stderr": ""}
        self._log_dirty = False
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._log_visible = False
        self._log_was_visible_before_results_expand = False

        super().__init__()

        # Treat Community Deposits like Hotspots and Planets: enabled by default.
        self.community_deposits_enabled.set(True)

        # In the final console-less EXE these streams provide the technical
        # details that would otherwise be invisible to the user.
        self._stdout_capture = _LogCapture(self, "stdout", self._original_stdout)
        self._stderr_capture = _LogCapture(self, "stderr", self._original_stderr)
        sys.stdout = self._stdout_capture
        sys.stderr = self._stderr_capture

        self.protocol("WM_DELETE_WINDOW", self._close_with_log_restore)
        self._append_log_line("INFO", "Log capture ready")
        self.after(250, self._refresh_log_view)

    def _build_ui(self):
        self.reference_system_var = tk.StringVar(master=self, value="")
        self.max_distance_var = tk.StringVar(master=self, value="50")
        self._distance_sort_state = {table: None for table in SORT_TABLES}
        self._body_sort_state = {table: None for table in SORT_TABLES}
        self._active_sort_column = {table: None for table in SORT_TABLES}
        super()._build_ui()

    def _build_filters(self, parent):
        super()._build_filters(parent)

        # Add Reference System / Max Distance beneath the existing Faction,
        # Power and Power State controls. Layout will be reorganized later.
        canvas = next(
            (
                child
                for child in parent.winfo_children()
                if isinstance(child, tk.Canvas)
            ),
            None,
        )
        if canvas is None:
            return

        children = canvas.winfo_children()
        if not children:
            return

        inner = children[0]

        tk.Label(
            inner,
            text="Reference system",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(anchor="w", padx=12, pady=(2, 0))

        reference_entry = tk.Entry(
            inner,
            textvariable=self.reference_system_var,
            bg="#3b3b3b",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
        )
        reference_entry.pack(fill="x", padx=12, pady=(2, 8), ipady=5)

        tk.Label(
            inner,
            text="Max distance (LY)",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(anchor="w", padx=12)

        max_distance_entry = tk.Entry(
            inner,
            textvariable=self.max_distance_var,
            bg="#3b3b3b",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
        )
        max_distance_entry.pack(fill="x", padx=12, pady=(2, 8), ipady=5)

        buttons = tk.Frame(inner, bg=COLORS["panel"])
        buttons.pack(fill="x", padx=12, pady=(2, 12))

        tk.Button(
            buttons,
            text="Clear",
            command=self._clear_scan_filters,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=12,
        ).pack(side="left")

    def _collect_config(self):
        config = super()._collect_config()

        max_distance = self.max_distance_var.get().strip()
        if not max_distance:
            max_distance = "50"
            self.max_distance_var.set(max_distance)

        config["reference_system"] = self.reference_system_var.get().strip()
        config["max_distance_ly"] = max_distance
        return config

    def _clear_scan_filters(self):
        # Keep the feature switches unchanged: Enable hotspots,
        # Enable planets and Show Community Deposits.
        for variables in (
            self.ring_vars,
            self.material_vars,
            self.planet_type_vars,
            self.power_state_vars,
        ):
            for variable in variables.values():
                variable.set(False)

        self.only_pristine.set(False)
        self.only_landables.set(False)
        self.faction_var.set("")
        self.power_var.set("")
        self.reference_system_var.set("")
        self.max_distance_var.set("50")

    @staticmethod
    def _move_distance_before_system(headers):
        headers = list(headers or [])
        if DISTANCE_COLUMN not in headers:
            return headers

        headers.remove(DISTANCE_COLUMN)
        try:
            system_index = headers.index("System")
        except ValueError:
            headers.insert(0, DISTANCE_COLUMN)
        else:
            headers.insert(system_index, DISTANCE_COLUMN)
        return headers

    def _scan_complete(self, result):
        # Keep Distance immediately before System in all result tabs.
        mapped = dict(result)
        for key in (
            "hotspot_headers",
            "planet_headers",
            "community_headers",
        ):
            mapped[key] = self._move_distance_before_system(
                result.get(key, [])
            )

        super()._scan_complete(mapped)

    def _scan_failed(self, message):
        self._append_log_line("ERROR", f"Scan failed: {message}")
        super()._scan_failed(message)

    def _rhino_upload_failed(self, message):
        self._append_log_line("ERROR", f"RhinoSpotter upload failed: {message}")
        super()._rhino_upload_failed(message)

    def _set_filter_dataset(self, table, headers, rows):
        headers = list(headers or [])

        self._distance_sort_state[table] = (
            "asc" if DISTANCE_COLUMN in headers else None
        )
        self._body_sort_state[table] = (
            "asc" if BODY_COLUMN in headers else None
        )

        # Reference searches start nearest-first. Without a Distance column,
        # Body starts alphabetically. Clicking either heading makes it the
        # active sort for that table.
        if DISTANCE_COLUMN in headers:
            self._active_sort_column[table] = DISTANCE_COLUMN
        elif BODY_COLUMN in headers:
            self._active_sort_column[table] = BODY_COLUMN
        else:
            self._active_sort_column[table] = None

        super()._set_filter_dataset(table, headers, rows)

    @staticmethod
    def _numeric_distance(row):
        value = row.get(DISTANCE_COLUMN, "")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _body_value(row):
        value = str(row.get(BODY_COLUMN, "") or "").strip()
        return value.casefold() if value else None

    def _sort_rows(self, table, rows):
        column = self._active_sort_column.get(table)
        if column == DISTANCE_COLUMN:
            direction = self._distance_sort_state.get(table)
            value_getter = self._numeric_distance
        elif column == BODY_COLUMN:
            direction = self._body_sort_state.get(table)
            value_getter = self._body_value
        else:
            return rows

        if direction not in ("asc", "desc"):
            return rows

        with_value = []
        without_value = []
        for row in rows:
            value = value_getter(row)
            if value is None:
                without_value.append(row)
            else:
                with_value.append((value, row))

        with_value.sort(
            key=lambda item: item[0],
            reverse=(direction == "desc"),
        )
        return [row for _value, row in with_value] + without_value

    @staticmethod
    def _compact_community_rows(rows):
        """Hide only consecutive duplicate system names in Community results."""

        compacted = []
        previous_system_key = None
        for row in rows:
            display_row = dict(row)
            system = str(display_row.get("System", "") or "").strip()
            system_key = system.casefold() if system else None

            if system_key is not None and system_key == previous_system_key:
                display_row["System"] = ""
            else:
                previous_system_key = system_key

            compacted.append(display_row)

        return compacted

    def _render_filtered_table(self, table):
        tree = self._table_trees[table]
        rows = [
            row for row in self._column_filter_rows.get(table, [])
            if self._row_matches(table, row)
        ]
        rows = self._sort_rows(table, rows)

        if table == "hotspots":
            display_rows = self._compact_hotspot_rows(rows)
        elif table == "planets":
            display_rows = self._compact_planet_rows(rows)
        elif table == "community":
            display_rows = self._compact_community_rows(rows)
        else:
            display_rows = rows

        self._populate_tree(
            tree,
            self._column_filter_headers.get(table, []),
            display_rows,
        )
        self._configure_filter_headings(table)

    def _configure_filter_headings(self, table):
        # Let the base class configure normal drop-down filters first, then
        # replace Body (and Distance) with direct click-to-sort headings.
        super()._configure_filter_headings(table)

        headers = self._column_filter_headers.get(table, [])
        tree = self._table_trees[table]
        active_column = self._active_sort_column.get(table)

        for column in (DISTANCE_COLUMN, BODY_COLUMN):
            if column not in headers:
                continue

            if column == DISTANCE_COLUMN:
                direction = self._distance_sort_state.get(table) or "asc"
            else:
                direction = self._body_sort_state.get(table) or "asc"

            if active_column == column:
                marker = " ▲" if direction == "asc" else " ▼"
            else:
                marker = " ↕"

            tree.heading(
                column,
                text=column + marker,
                command=lambda t=table, c=column: self._toggle_direct_sort(t, c),
            )

    def _toggle_direct_sort(self, table, column):
        if self._active_sort_column.get(table) == column:
            if column == DISTANCE_COLUMN:
                current = self._distance_sort_state.get(table) or "asc"
                self._distance_sort_state[table] = (
                    "desc" if current == "asc" else "asc"
                )
            else:
                current = self._body_sort_state.get(table) or "asc"
                self._body_sort_state[table] = (
                    "desc" if current == "asc" else "asc"
                )
        else:
            self._active_sort_column[table] = column
            if column == DISTANCE_COLUMN:
                self._distance_sort_state[table] = "asc"
            else:
                self._body_sort_state[table] = "asc"

        self._render_filtered_table(table)

    def _autosize_single_column(self, tree, column, rows=None):
        super()._autosize_single_column(tree, column, rows=rows)
        if column in (DISTANCE_COLUMN, BODY_COLUMN):
            try:
                current_width = int(tree.column(column, "width"))
                tree.column(column, width=current_width + 18)
            except (tk.TclError, TypeError, ValueError):
                pass

    def _build_results(self, parent):
        super()._build_results(parent)

        self._results_panel = parent
        self._results_expanded = False
        self._saved_sashes = None

        self.expand_results_button = tk.Button(
            parent,
            text="Expand Results",
            command=self._toggle_results_expansion,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=10,
            pady=3,
        )
        self.expand_results_button.place(relx=1.0, x=-14, y=8, anchor="ne")

    def _build_bottom_bar(self):
        """Build the normal controls plus a compact in-app log viewer."""
        before = set(self.winfo_children())
        super()._build_bottom_bar()
        created = [child for child in self.winfo_children() if child not in before]
        self._bottom_bar = created[-1] if created else None

        if self._bottom_bar is not None:
            self.log_details_button = tk.Button(
                self._bottom_bar,
                text="Show Log Details",
                command=self._toggle_log_details,
                bg="#30363c",
                fg=COLORS["muted"],
                activebackground="#3d464e",
                activeforeground=COLORS["text"],
                relief="flat",
                font=("Segoe UI", 8),
                padx=7,
                pady=2,
            )
            self.log_details_button.pack(
                side="right",
                padx=(6, 12),
                pady=16,
            )

        self._log_panel = tk.Frame(self, bg="#202326", height=190)
        self._log_panel.pack_propagate(False)

        log_header = tk.Frame(self._log_panel, bg="#202326")
        log_header.pack(fill="x", padx=10, pady=(6, 4))

        tk.Label(
            log_header,
            text="LOG DETAILS",
            bg="#202326",
            fg=COLORS["orange"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        tk.Button(
            log_header,
            text="Copy Log",
            command=self._copy_log,
            bg="#30363c",
            fg=COLORS["text"],
            activebackground="#3d464e",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
            padx=7,
            pady=1,
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            log_header,
            text="Clear Log",
            command=self._clear_log,
            bg="#30363c",
            fg=COLORS["text"],
            activebackground="#3d464e",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
            padx=7,
            pady=1,
        ).pack(side="right")

        log_frame = tk.Frame(self._log_panel, bg="#202326")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._log_text = tk.Text(
            log_frame,
            bg="#17191b",
            fg="#d7d7d7",
            insertbackground=COLORS["text"],
            relief="flat",
            wrap="none",
            font=("Consolas", 9),
            state="disabled",
        )
        log_y = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self._log_text.yview,
            style="Vertical.TScrollbar",
        )
        log_x = ttk.Scrollbar(
            log_frame,
            orient="horizontal",
            command=self._log_text.xview,
            style="Horizontal.TScrollbar",
        )
        self._log_text.configure(
            yscrollcommand=log_y.set,
            xscrollcommand=log_x.set,
        )
        self._log_text.grid(row=0, column=0, sticky="nsew")
        log_y.grid(row=0, column=1, sticky="ns")
        log_x.grid(row=1, column=0, sticky="ew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=0, minsize=9)
        log_frame.columnconfigure(0, weight=1)

    def _capture_log_text(self, channel, text):
        if not text:
            return

        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
        with self._log_lock:
            pending = self._log_partial.get(channel, "") + normalized
            parts = pending.split("\n")
            self._log_partial[channel] = parts.pop()

            for line in parts:
                clean = line.rstrip()
                if not clean:
                    continue
                level = "ERR" if channel == "stderr" else "LOG"
                timestamp = datetime.now().strftime("%H:%M:%S")
                self._log_lines.append(f"[{timestamp}] {level}  {clean}")
                self._log_dirty = True

    def _append_log_line(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self._log_lock:
            self._log_lines.append(f"[{timestamp}] {level}  {message}")
            self._log_dirty = True

    def _log_snapshot(self):
        with self._log_lock:
            lines = list(self._log_lines)
            for channel, partial in self._log_partial.items():
                if partial.strip():
                    level = "ERR" if channel == "stderr" else "LOG"
                    lines.append(f"{level}  {partial.rstrip()}")
        return "\n".join(lines)

    def _refresh_log_view(self):
        try:
            with self._log_lock:
                dirty = self._log_dirty
                self._log_dirty = False

            if dirty and hasattr(self, "_log_text"):
                content = self._log_snapshot()
                self._log_text.configure(state="normal")
                self._log_text.delete("1.0", "end")
                self._log_text.insert("1.0", content)
                self._log_text.configure(state="disabled")
                if self._log_visible:
                    self._log_text.see("end")

            self.after(250, self._refresh_log_view)
        except tk.TclError:
            return

    def _toggle_log_details(self):
        if self._log_visible:
            self._hide_log_panel()
        else:
            self._show_log_panel()

    def _show_log_panel(self):
        if self._results_expanded:
            return
        self._log_panel.pack(fill="x", side="bottom")
        self._log_visible = True
        self.log_details_button.configure(text="Hide Log Details")
        self._log_text.see("end")

    def _hide_log_panel(self):
        self._log_panel.pack_forget()
        self._log_visible = False
        if hasattr(self, "log_details_button"):
            self.log_details_button.configure(text="Show Log Details")

    def _copy_log(self):
        content = self._log_snapshot()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update_idletasks()

    def _clear_log(self):
        with self._log_lock:
            self._log_lines.clear()
            self._log_partial = {"stdout": "", "stderr": ""}
            self._log_dirty = True
        self._append_log_line("INFO", "Log cleared")

    def _close_with_log_restore(self):
        if sys.stdout is getattr(self, "_stdout_capture", None):
            sys.stdout = self._original_stdout
        if sys.stderr is getattr(self, "_stderr_capture", None):
            sys.stderr = self._original_stderr
        self.destroy()

    def _toggle_results_expansion(self):
        try:
            paned = self._results_panel.master
            panes = list(paned.panes())
            if len(panes) < 3:
                return

            left_panel = panes[0]
            systems_panel = panes[1]

            if not self._results_expanded:
                try:
                    self._saved_sashes = (
                        paned.sash_coord(0)[0],
                        paned.sash_coord(1)[0],
                    )
                except tk.TclError:
                    self._saved_sashes = None

                paned.paneconfigure(left_panel, hide=True)
                paned.paneconfigure(systems_panel, hide=True)

                self._log_was_visible_before_results_expand = self._log_visible
                if self._log_visible:
                    self._log_panel.pack_forget()

                if getattr(self, "_bottom_bar", None) is not None:
                    self._bottom_bar.pack_forget()

                self._results_expanded = True
                self.expand_results_button.configure(text="Restore Panels")
            else:
                paned.paneconfigure(left_panel, hide=False)
                paned.paneconfigure(systems_panel, hide=False)

                if getattr(self, "_bottom_bar", None) is not None:
                    self._bottom_bar.pack(fill="x", side="bottom")

                if self._log_was_visible_before_results_expand:
                    self._log_panel.pack(fill="x", side="bottom")
                    self._log_visible = True
                    self.log_details_button.configure(text="Hide Log Details")

                self._results_expanded = False
                self.expand_results_button.configure(text="Expand Results")

                if self._saved_sashes:
                    first_x, second_x = self._saved_sashes

                    def _restore_sashes():
                        try:
                            paned.sash_place(0, first_x, 0)
                            paned.sash_place(1, second_x, 0)
                        except tk.TclError:
                            pass

                    self.after_idle(_restore_sashes)

        except (AttributeError, tk.TclError):
            return


def main():
    app = FinderV8ExpandResultsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
