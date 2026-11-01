#!/usr/bin/env python3

"""v8 feature test: filters directly in result-table column headers."""

import tkinter as tk
import tkinter.font as tkfont

from hotspots_finder_gui_v8_community import FinderV8CommunityApp

FILTER_COLUMNS = {
    "community": ("System", "Body", "Commodity", "Rigs", "Amount", "Density"),
    "planets": ("System", "Status", "Planet Type", "Landable", "Volcanism"),
    "hotspots": ("System", "Status", "Body", "Ring Type", "Reserve Level", "Commodity"),
}

class FinderV8ColumnFiltersApp(FinderV8CommunityApp):
    def _build_ui(self):
        self._column_filter_rows = {}
        self._column_filter_headers = {}
        self._column_filter_state = {
            table: {column: None for column in columns}
            for table, columns in FILTER_COLUMNS.items()
        }
        self._autosize_next_populate = set()
        super()._build_ui()

        # Keep the systems pane narrower than the original v8 layout, but wide
        # enough to match the proportions used in the current UI mockup.
        self._configure_compact_systems_panel()

        # Pasting systems one at a time automatically moves the cursor to the
        # next line, making repeated copy/paste entry quicker.
        self.systems_text.bind("<<Paste>>", self._paste_systems_with_newline)

    def _configure_compact_systems_panel(self):
        try:
            systems_panel = self.systems_text.master.master
            paned = systems_panel.master
            systems_panel.configure(width=245)
            paned.paneconfigure(systems_panel, minsize=220)

            def _shrink_after_layout():
                try:
                    first_x, _first_y = paned.sash_coord(0)
                    paned.sash_place(1, first_x + 250, 0)
                except (tk.TclError, IndexError):
                    pass

            self.after_idle(_shrink_after_layout)
        except (AttributeError, tk.TclError):
            pass

    def _paste_systems_with_newline(self, _event=None):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return "break"

        text = str(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return "break"

        try:
            self.systems_text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

        insert_text = "\n".join(lines) + "\n"
        self.systems_text.insert("insert", insert_text)
        self.systems_text.see("insert")
        self._refresh_system_count()
        return "break"

    def _build_results(self, parent):
        super()._build_results(parent)

        # The old temporary Body/Commodity combobox bar is no longer needed.
        children = self.community_tab.winfo_children()
        if children:
            children[0].pack_forget()

        self._table_trees = {
            "hotspots": self.hotspot_tree,
            "planets": self.planet_tree,
            "community": self.community_tree,
        }

        for tree in self._table_trees.values():
            tree.bind("<Double-Button-1>", self._tree_double_click_autosize, add="+")

    def _scan_complete(self, result):
        # A fresh scan gets a fresh content-based column fit. Later filtering
        # preserves whatever widths the user has manually chosen.
        self._autosize_next_populate.update(
            {self.hotspot_tree, self.planet_tree, self.community_tree}
        )

        # Display terminology: hotspot "Material" becomes "Commodity".
        mapped = dict(result)
        hotspot_headers = [
            "Commodity" if header == "Material" else header
            for header in result.get("hotspot_headers", [])
        ]
        hotspot_rows = []
        for source in result.get("hotspot_rows", []):
            row = dict(source)
            if "Material" in row:
                row["Commodity"] = row.pop("Material")
            hotspot_rows.append(row)

        mapped["hotspot_headers"] = hotspot_headers
        mapped["hotspot_rows"] = hotspot_rows

        super()._scan_complete(mapped)

        self._set_filter_dataset(
            "hotspots",
            hotspot_headers,
            hotspot_rows,
        )
        self._set_filter_dataset(
            "planets",
            mapped.get("planet_headers", []),
            mapped.get("planet_rows", []),
        )

    def _set_community_results(self, headers, rows):
        # Keep the already-tested Community Deposits storage/upload behavior.
        super()._set_community_results(headers, rows)
        if hasattr(self, "_table_trees"):
            self._set_filter_dataset("community", headers, rows)

    def _set_filter_dataset(self, table, headers, rows):
        headers = list(headers or [])
        rows = [dict(row) for row in (rows or [])]

        self._column_filter_headers[table] = headers
        self._column_filter_rows[table] = self._effective_rows(table, rows)
        self._column_filter_state[table] = {
            column: None for column in FILTER_COLUMNS[table]
        }
        self._render_filtered_table(table)

    def _effective_rows(self, table, rows):
        """Restore repeated values hidden by the compact result display."""

        if table == "community":
            return rows

        if table == "planets":
            fill_columns = ("System", "Distance (LY)", "Status")
        else:
            fill_columns = (
                "System",
                "Distance (LY)",
                "Status",
                "Body",
                "Ring",
                "Ring Type",
                "Reserve Level",
                "LS Distance",
            )

        effective = []
        context = {}
        for source in rows:
            row = dict(source)

            if str(row.get("System", "")).strip():
                context = {}

            for column in fill_columns:
                value = row.get(column, "")
                if value not in (None, ""):
                    context[column] = value
                elif column in context:
                    row[column] = context[column]

            effective.append(row)

        return effective

    @staticmethod
    def _filter_value(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _filter_label(value):
        return "(Blank)" if value == "" else value

    def _row_matches(self, table, row, *, skip_column=None):
        for column, selected in self._column_filter_state[table].items():
            if column == skip_column or selected is None:
                continue
            if self._filter_value(row.get(column, "")) != selected:
                return False
        return True

    def _choices_for_column(self, table, column):
        values = {
            self._filter_value(row.get(column, ""))
            for row in self._column_filter_rows.get(table, [])
            if self._row_matches(table, row, skip_column=column)
        }
        return sorted(
            values,
            key=lambda value: (value != "", value.casefold()),
        )

    def _render_filtered_table(self, table):
        tree = self._table_trees[table]
        rows = [
            row for row in self._column_filter_rows.get(table, [])
            if self._row_matches(table, row)
        ]

        if table == "hotspots":
            display_rows = self._compact_hotspot_rows(rows)
        elif table == "planets":
            display_rows = self._compact_planet_rows(rows)
        else:
            display_rows = rows

        self._populate_tree(
            tree,
            self._column_filter_headers.get(table, []),
            display_rows,
        )
        self._configure_filter_headings(table)

    def _populate_tree(self, tree, headers, rows):
        """Populate a table without undoing user-selected column widths.

        On a new scan columns are fitted to their heading/content. Filtering
        then keeps the current widths, including any manual drag-resizing.
        """

        headers = list(headers)
        old_headers = list(tree["columns"])
        old_widths = {}
        if old_headers == headers:
            for header in headers:
                try:
                    old_widths[header] = int(tree.column(header, "width"))
                except (tk.TclError, TypeError, ValueError):
                    pass

        tree.delete(*tree.get_children())
        tree["columns"] = headers

        for header in headers:
            tree.heading(header, text=header, command="")
            tree.column(
                header,
                minwidth=55,
                stretch=False,
                anchor="center" if header == "Distance (LY)" else "w",
            )

        for row in rows:
            values = [row.get(header, "") for header in headers]
            tree.insert("", "end", values=values)

        should_autosize = tree in self._autosize_next_populate or not old_widths
        if should_autosize:
            self._autosize_tree_columns(tree, headers, rows)
            self._autosize_next_populate.discard(tree)
        else:
            for header, width in old_widths.items():
                tree.column(header, width=width)

    def _autosize_tree_columns(self, tree, headers, rows):
        for header in headers:
            self._autosize_single_column(tree, header, rows=rows)

    def _autosize_single_column(self, tree, column, rows=None):
        font = tkfont.nametofont("TkDefaultFont")
        heading_font = tkfont.Font(font=font)

        table = None
        for table_name, table_tree in getattr(self, "_table_trees", {}).items():
            if table_tree is tree:
                table = table_name
                break

        filterable = table is not None and column in FILTER_COLUMNS.get(table, ())
        active = (
            filterable
            and self._column_filter_state.get(table, {}).get(column) is not None
        )
        if filterable:
            heading_text = str(column) + (" ▼*" if active else " ▼")
        else:
            heading_text = str(column)

        width = heading_font.measure(heading_text) + 24

        if rows is None:
            values = [tree.set(iid, column) for iid in tree.get_children("")]
        else:
            values = [row.get(column, "") for row in rows]

        for value in values:
            text = str(value or "")
            width = max(width, font.measure(text) + 24)

        width = max(70, min(width, 360))
        tree.column(column, width=width, minwidth=55, stretch=False)

    def _tree_double_click_autosize(self, event):
        tree = event.widget
        try:
            if tree.identify_region(event.x, event.y) != "separator":
                return None

            column_id = tree.identify_column(event.x)
            if not column_id or not column_id.startswith("#"):
                return "break"

            index = int(column_id[1:]) - 1
            columns = list(tree["columns"])
            if index < 0 or index >= len(columns):
                return "break"

            self._autosize_single_column(tree, columns[index])
            return "break"
        except (tk.TclError, TypeError, ValueError):
            return "break"

    @staticmethod
    def _compact_planet_rows(rows):
        result = []
        previous_system = None

        for source in rows:
            row = dict(source)
            system = row.get("System", "")
            if system == previous_system:
                row["System"] = ""
                row["Distance (LY)"] = ""
                row["Status"] = ""
            else:
                previous_system = system
            result.append(row)

        return result

    @staticmethod
    def _compact_hotspot_rows(rows):
        result = []
        previous_system = None
        previous_ring_key = None

        for source in rows:
            row = dict(source)
            system = row.get("System", "")
            body = row.get("Body", "")
            ring = row.get("Ring", "")
            ring_key = (system, body, ring)

            if system == previous_system:
                row["System"] = ""
                row["Distance (LY)"] = ""
            else:
                previous_system = system
                previous_ring_key = None

            if ring and ring_key == previous_ring_key:
                for column in (
                    "Status",
                    "Body",
                    "Ring",
                    "Ring Type",
                    "Reserve Level",
                    "LS Distance",
                ):
                    row[column] = ""
            elif ring:
                previous_ring_key = ring_key

            result.append(row)

        return result

    def _configure_filter_headings(self, table):
        tree = self._table_trees[table]
        filterable = set(FILTER_COLUMNS[table])

        for column in self._column_filter_headers.get(table, []):
            if column in filterable:
                active = self._column_filter_state[table].get(column) is not None
                marker = " ▼*" if active else " ▼"
                tree.heading(
                    column,
                    text=column + marker,
                    command=lambda t=table, c=column: self._show_column_filter(t, c),
                )
            else:
                tree.heading(column, text=column, command="")

    def _show_column_filter(self, table, column):
        selected = self._column_filter_state[table].get(column)
        choices = self._choices_for_column(table, column)

        menu = tk.Menu(self, tearoff=False)

        all_label = "✓ All" if selected is None else "All"
        menu.add_command(
            label=all_label,
            command=lambda: self._set_column_filter(table, column, None),
        )
        menu.add_separator()

        for index, value in enumerate(choices):
            label = self._filter_label(value)
            if value == selected:
                label = "✓ " + label
            menu.add_command(
                label=label,
                columnbreak=(index > 0 and index % 28 == 0),
                command=lambda v=value: self._set_column_filter(table, column, v),
            )

        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _set_column_filter(self, table, column, value):
        self._column_filter_state[table][column] = value
        self._render_filtered_table(table)


def main():
    app = FinderV8ColumnFiltersApp()
    app.mainloop()


if __name__ == "__main__":
    main()
