#!/usr/bin/env python3

"""v8 GUI entry point with Community Deposits support.

Kept as a thin layer over the already-tested v8 interface while features are
being completed. The GUI can be consolidated/refined after functionality is
finished.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import community_deposits
import results_export
import rhinospotter_sync_service
from edmc_plugin.EDHF_Community_Navigator.sync_preview_dialog import show_sync_preview
from hotspots_finder_gui_v8 import APP_TITLE, COLORS, FinderV8App


COMMUNITY_FALLBACK_HEADERS = list(community_deposits.COMMUNITY_HEADERS)


class FinderV8CommunityApp(FinderV8App):
    def _build_ui(self):
        self.community_deposits_enabled = tk.BooleanVar(master=self, value=False)
        self.community_commodity_filter = tk.StringVar(master=self, value="All")
        self.community_body_filter = tk.StringVar(master=self, value="All")
        self.community_all_headers = list(COMMUNITY_FALLBACK_HEADERS)
        self.community_all_rows = []
        self.rhino_upload_running = False
        super()._build_ui()

    def _build_systems(self, parent):
        super()._build_systems(parent)

        community = tk.Frame(parent, bg=COLORS["panel"])
        community.pack(fill="x", padx=12, pady=(0, 12))

        tk.Label(
            community,
            text="COMMUNITY DEPOSITS",
            bg=COLORS["panel"],
            fg=COLORS["orange"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        tk.Checkbutton(
            community,
            text="Show Community Deposits",
            variable=self.community_deposits_enabled,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["panel"],
            activeforeground=COLORS["text"],
            selectcolor="#404040",
            highlightthickness=0,
            bd=0,
            anchor="w",
        ).pack(fill="x")

        self.rhino_upload_button = tk.Button(
            community,
            text="Upload RhinoSpotter Deposits",
            command=self.start_rhino_upload,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            disabledforeground="#777777",
            relief="flat",
            padx=10,
            pady=5,
        )
        self.rhino_upload_button.pack(fill="x", pady=(6, 0))

        tk.Label(
            community,
            text=(
                "Reads deposits from the shared Cloudflare database for the "
                "selected systems. Upload reads RhinoSpotter local bookmarks."
            ),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=245,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

    def _build_results(self, parent):
        super()._build_results(parent)

        self.community_tab = tk.Frame(self.notebook, bg=COLORS["panel"])
        self.notebook.add(self.community_tab, text="Community Deposits")

        filter_bar = tk.Frame(self.community_tab, bg=COLORS["panel"])
        filter_bar.pack(fill="x", padx=6, pady=(6, 4))

        tk.Label(
            filter_bar,
            text="Commodity",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(side="left", padx=(0, 5))

        self.community_commodity_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.community_commodity_filter,
            values=["All"],
            state="readonly",
            width=18,
        )
        self.community_commodity_combo.pack(side="left", padx=(0, 14))
        self.community_commodity_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._community_filter_changed(),
        )

        tk.Label(
            filter_bar,
            text="Body",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(side="left", padx=(0, 5))

        self.community_body_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.community_body_filter,
            values=["All"],
            state="readonly",
            width=24,
        )
        self.community_body_combo.pack(side="left")
        self.community_body_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._community_filter_changed(),
        )

        self.community_tree = self._make_tree(self.community_tab)

        export_bar = tk.Frame(parent, bg=COLORS["panel"])
        export_bar.pack(fill="x", padx=12, pady=(0, 12))

        tk.Label(
            export_bar,
            text="Export current tab:",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
        ).pack(side="left", padx=(0, 7))

        tk.Button(
            export_bar,
            text="CSV",
            command=self.export_current_csv,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=12,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            export_bar,
            text="XLSX",
            command=self.export_current_xlsx,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=12,
        ).pack(side="left")

    def _collect_config(self):
        config = super()._collect_config()
        config["community_deposits_enabled"] = self.community_deposits_enabled.get()
        return config

    def _scan_complete(self, result):
        super()._scan_complete(result)
        self._set_community_results(
            result.get("community_headers") or COMMUNITY_FALLBACK_HEADERS,
            result.get("community_rows", []),
        )

    def _set_community_results(self, headers, rows):
        self.community_all_headers = list(headers or COMMUNITY_FALLBACK_HEADERS)
        self.community_all_rows = list(rows or [])

        self.community_commodity_filter.set("All")
        self.community_body_filter.set("All")
        self._refresh_community_filter_values()
        self._apply_community_filters()

    def _community_filter_changed(self):
        self._refresh_community_filter_values()
        self._apply_community_filters()

    def _refresh_community_filter_values(self):
        rows = self.community_all_rows

        selected_commodity = self.community_commodity_filter.get() or "All"
        selected_body = self.community_body_filter.get() or "All"

        commodity_source = rows
        if selected_body != "All":
            commodity_source = [
                row for row in rows
                if str(row.get("Body", "")) == selected_body
            ]

        commodity_values = sorted(
            {
                str(row.get("Commodity", "")).strip()
                for row in commodity_source
                if str(row.get("Commodity", "")).strip()
            },
            key=str.casefold,
        )
        commodity_choices = ["All"] + commodity_values
        self.community_commodity_combo["values"] = commodity_choices
        if selected_commodity not in commodity_choices:
            selected_commodity = "All"
            self.community_commodity_filter.set("All")

        body_source = rows
        if selected_commodity != "All":
            body_source = [
                row for row in rows
                if str(row.get("Commodity", "")) == selected_commodity
            ]

        body_values = sorted(
            {
                str(row.get("Body", "")).strip()
                for row in body_source
                if str(row.get("Body", "")).strip()
            },
            key=str.casefold,
        )
        body_choices = ["All"] + body_values
        self.community_body_combo["values"] = body_choices
        if selected_body not in body_choices:
            self.community_body_filter.set("All")

    def _apply_community_filters(self):
        commodity = self.community_commodity_filter.get() or "All"
        body = self.community_body_filter.get() or "All"

        rows = []
        for row in self.community_all_rows:
            if commodity != "All" and str(row.get("Commodity", "")) != commodity:
                continue
            if body != "All" and str(row.get("Body", "")) != body:
                continue
            rows.append(row)

        # Match the compact display used by the other result tabs: keep the
        # System name on the first visible row of each consecutive group and
        # blank it on following rows from the same system. Work on copies so
        # the underlying Community data remains complete for filtering/export
        # helpers and the active layout can still retain the real row system.
        display_rows = []
        previous_system = None
        for row in rows:
            display_row = dict(row)
            system = str(display_row.get("System", "") or "").strip()
            system_key = system.casefold()
            if system and previous_system == system_key:
                display_row["System"] = ""
            elif system:
                previous_system = system_key
            else:
                previous_system = None
            display_rows.append(display_row)

        self._populate_tree(
            self.community_tree,
            self.community_all_headers,
            display_rows,
        )

    def _current_export_source(self):
        selected = self.notebook.select()

        if selected == str(self.hotspot_tab):
            return "Hotspots", self.hotspot_tree
        if selected == str(self.planet_tab):
            return "Planets", self.planet_tree
        if selected == str(self.community_tab):
            return "Community Deposits", self.community_tree

        return "Results", None

    def _visible_tree_data(self, tree):
        if tree is None:
            return [], []

        headers = list(tree["columns"])
        rows = [
            [tree.set(iid, header) for header in headers]
            for iid in tree.get_children("")
        ]
        return headers, rows

    def export_current_csv(self):
        label, tree = self._current_export_source()
        headers, rows = self._visible_tree_data(tree)

        if not headers or not rows:
            messagebox.showwarning(
                APP_TITLE,
                f"There are no visible {label} results to export.",
                parent=self,
            )
            return

        initial_name = label.lower().replace(" ", "_") + ".csv"
        path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export {label} as CSV",
            defaultextension=".csv",
            initialfile=initial_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            results_export.write_csv(path, headers, rows)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return

        self.status_var.set(f"Exported {len(rows)} rows to CSV")
        messagebox.showinfo(
            APP_TITLE,
            f"Exported {len(rows)} visible rows from {label}.\n\n{path}",
            parent=self,
        )

    def export_current_xlsx(self):
        label, tree = self._current_export_source()
        headers, rows = self._visible_tree_data(tree)

        if not headers or not rows:
            messagebox.showwarning(
                APP_TITLE,
                f"There are no visible {label} results to export.",
                parent=self,
            )
            return

        initial_name = label.lower().replace(" ", "_") + ".xlsx"
        path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export {label} as XLSX",
            defaultextension=".xlsx",
            initialfile=initial_name,
            filetypes=[("Excel workbooks", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            results_export.write_xlsx(
                path,
                headers,
                rows,
                sheet_name=label,
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return

        self.status_var.set(f"Exported {len(rows)} rows to XLSX")
        messagebox.showinfo(
            APP_TITLE,
            f"Exported {len(rows)} visible rows from {label}.\n\n{path}",
            parent=self,
        )

    def start_rhino_upload(self):
        if self.rhino_upload_running:
            return

        if self.running:
            messagebox.showwarning(
                APP_TITLE,
                "Wait for the current scan to finish before uploading RhinoSpotter deposits.",
                parent=self,
            )
            return

        self.rhino_upload_running = True
        self.rhino_upload_button.configure(state="disabled")
        self.scan_button.configure(state="disabled")
        self.progress.start(12)
        self.status_var.set("Preparing RhinoSpotter sync preview...")

        systems = self._system_list()
        refresh_after_upload = self.community_deposits_enabled.get() and bool(systems)

        threading.Thread(
            target=self._rhino_preview_worker,
            args=(systems, refresh_after_upload),
            daemon=True,
        ).start()

    def _rhino_sync_preview(self):
        return rhinospotter_sync_service.preview_sync()

    def _rhino_preview_worker(self, systems, refresh_after_upload):
        try:
            plan = self._rhino_sync_preview()
            self.after(0, self._rhino_preview_ready, plan, systems, refresh_after_upload)
        except Exception as exc:
            self.after(0, self._rhino_upload_failed, str(exc))

    def _rhino_preview_ready(self, plan, systems, refresh_after_upload):
        theme_name = str(
            (getattr(self, "v8_settings", {}).get("application", {}) or {}).get(
                "theme", "deep_black"
            )
        )
        palette = visual_theme.THEMES.get(theme_name, visual_theme.THEMES["deep_black"])
        confirmed = show_sync_preview(self, plan, palette=palette)
        if not confirmed:
            self._finish_rhino_upload("RhinoSpotter sync cancelled")
            return
        threading.Thread(
            target=self._rhino_upload_worker,
            args=(systems, refresh_after_upload, plan["snapshot"]),
            daemon=True,
        ).start()

    def _rhino_upload_worker(self, systems, refresh_after_upload, expected_snapshot):
        try:
            summary = rhinospotter_sync_service.confirm_sync(
                None, expected_snapshot
            )
            if summary.get("stale"):
                self.after(
                    0, self._rhino_preview_ready, summary["plan"],
                    systems, refresh_after_upload,
                )
                return

            community_headers = []
            community_rows = []
            remote_changed = any(
                int(summary.get(key, 0) or 0) > 0
                for key in ("inserted", "matched", "updated")
            )
            if refresh_after_upload and remote_changed:
                community_headers, community_rows = (
                    community_deposits.fetch_deposits_for_systems(
                        systems,
                        commander=self.v8_settings.get("community_api", {}).get("commander"),
                    )
                )

            self.after(
                0,
                self._rhino_upload_complete,
                summary,
                community_headers,
                community_rows,
            )
        except Exception as exc:
            self.after(0, self._rhino_upload_failed, str(exc))

    def _rhino_upload_complete(self, summary, community_headers, community_rows):
        if community_headers or community_rows:
            self._set_community_results(
                community_headers or COMMUNITY_FALLBACK_HEADERS,
                community_rows,
            )

        from edmc_plugin.EDHF_Community_Navigator.batch_protocol import outcome_summary, sync_failure_text
        text = outcome_summary(summary)
        detail = sync_failure_text(summary, retry_command="Upload RhinoSpotter Deposits")
        incomplete = bool(summary.get("errors") or summary.get("skipped") or summary.get("pending_reports") or summary.get("state_error"))
        self._finish_rhino_upload(text)
        notify = messagebox.showwarning if incomplete else messagebox.showinfo
        notify(APP_TITLE, text + ("\n\n" + detail if detail else ""), parent=self)

    def _community_credentials_changed(self, commander):
        generation = getattr(self, "_community_credentials_generation", 0) + 1
        self._community_credentials_generation = generation
        self._set_community_results(COMMUNITY_FALLBACK_HEADERS, [])
        self.status_var.set("Verifying the new Community API Key…")
        def apply(headers, rows, error=None):
            if self._community_credentials_generation != generation:
                return
            self._set_community_results(headers or COMMUNITY_FALLBACK_HEADERS, rows)
            self.status_var.set("Community API Key could not be verified" if error else "Community API Key verified")
        def verify():
            try:
                headers, rows = community_deposits.fetch_all_deposits(commander=commander)
            except Exception:
                self.after(0, apply, None, [], True)
            else:
                self.after(0, apply, headers, rows)
        threading.Thread(target=verify, daemon=True, name="Finder-Credential-Check").start()

    def _rhino_upload_failed(self, message):
        self._finish_rhino_upload("RhinoSpotter upload error")
        messagebox.showerror(APP_TITLE, message, parent=self)

    def _finish_rhino_upload(self, status):
        self.rhino_upload_running = False
        self.progress.stop()
        self.rhino_upload_button.configure(state="normal")
        self.scan_button.configure(state="normal")
        self.status_var.set(status)


# Import after the community base class exists: the visual inheritance chain
# imports the column-filter layer, which derives from FinderV8CommunityApp.
import hotspots_finder_gui_v8_visual as visual_theme


def main():
    app = FinderV8CommunityApp()
    app.mainloop()


if __name__ == "__main__":
    main()
