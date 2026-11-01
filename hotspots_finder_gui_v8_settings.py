#!/usr/bin/env python3

"""Settings mixin for the active v8 desktop interface."""

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import app_settings
import community_deposits
import rhinospotter_sync_service
import ui_scale_runtime
from hotspots_finder_gui_v8 import APP_TITLE, COLORS


def settings_window_metrics(
    scale,
    screen_height,
    preferred_height=700,
    screen_width=None,
    preferred_width=600,
):
    """Return screen-fitted Settings geometry without a scrolling viewport."""
    scale = ui_scale_runtime.normalise_scale(scale)
    physical_width = int(round(preferred_width * scale))
    if screen_width is not None:
        physical_width = min(physical_width, max(240, int(screen_width) - 40))
    physical_height = min(
        int(round(preferred_height * scale)),
        max(320, int(screen_height) - 40),
    )
    logical_width = max(1, int(round(physical_width / scale)))
    logical_height = max(1, int(round(physical_height / scale)))
    compact_layout = logical_height < 660
    return {
        "physical_width": physical_width,
        "physical_height": physical_height,
        "logical_width": logical_width,
        "logical_height": logical_height,
        "compact_layout": compact_layout,
        "actions_y": logical_height - (29 if compact_layout else 43),
    }


class FinderV8SettingsMixin:
    """Persistent startup and RhinoSpotter settings for the active v8 GUI."""

    def _load_v8_settings_state(self):
        self.v8_settings = app_settings.load_settings()
        self._refresh_runtime_settings()

    def _refresh_runtime_settings(self):
        rhino = self.v8_settings.get("rhinospotter", {})
        self.rhinospotter_data_path = str(
            app_settings.resolve_rhinospotter_data_path(self.v8_settings)
        )
        self.ask_before_rhino_sync = bool(rhino.get("ask_before_sync", True))

    @staticmethod
    def _format_distance(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "50"
        return f"{number:g}"

    @staticmethod
    def _path_key(value):
        text = str(value or "").strip()
        if not text:
            return ""
        return os.path.normcase(os.path.abspath(os.path.expanduser(text)))

    def _apply_startup_settings(self):
        startup = self.v8_settings.get("startup", {})
        remember = bool(startup.get("remember_last_filters", False))
        last_filters = self.v8_settings.get("last_filters", {})

        if remember and isinstance(last_filters, dict) and last_filters:
            self._apply_saved_filters(last_filters)
            return

        self.hotspots_enabled.set(bool(startup.get("hotspots_enabled", True)))
        self.planets_enabled.set(bool(startup.get("planets_enabled", True)))
        self.community_deposits_enabled.set(
            bool(startup.get("community_deposits_enabled", True))
        )
        self.max_distance_var.set(
            self._format_distance(startup.get("max_distance_ly", 50.0))
        )

    def _apply_saved_filters(self, values):
        self.hotspots_enabled.set(bool(values.get("hotspots_enabled", True)))
        self.only_pristine.set(bool(values.get("only_pristine", False)))
        self.planets_enabled.set(bool(values.get("planets_enabled", True)))
        self.only_landables.set(bool(values.get("only_landables", False)))
        self.community_deposits_enabled.set(
            bool(values.get("community_deposits_enabled", True))
        )

        for key, variable in self.ring_vars.items():
            variable.set(bool(values.get("ring_types", {}).get(key, False)))
        for key, variable in self.material_vars.items():
            variable.set(bool(values.get("materials", {}).get(key, False)))
        for key, variable in self.planet_type_vars.items():
            variable.set(bool(values.get("planet_types", {}).get(key, False)))
        for key, variable in self.power_state_vars.items():
            variable.set(bool(values.get("power_states", {}).get(key, False)))

        self.faction_var.set(str(values.get("faction_name", "") or ""))
        self.power_var.set(str(values.get("power_name", "") or ""))
        self.reference_system_var.set(
            str(values.get("reference_system", "") or "")
        )
        self.max_distance_var.set(
            self._format_distance(values.get("max_distance_ly", 50.0))
        )

    def _capture_current_filters(self):
        return {
            "hotspots_enabled": bool(self.hotspots_enabled.get()),
            "only_pristine": bool(self.only_pristine.get()),
            "ring_types": {
                key: bool(variable.get()) for key, variable in self.ring_vars.items()
            },
            "materials": {
                key: bool(variable.get())
                for key, variable in self.material_vars.items()
            },
            "planets_enabled": bool(self.planets_enabled.get()),
            "only_landables": bool(self.only_landables.get()),
            "planet_types": {
                key: bool(variable.get())
                for key, variable in self.planet_type_vars.items()
            },
            "community_deposits_enabled": bool(
                self.community_deposits_enabled.get()
            ),
            "faction_name": str(self.faction_var.get() or "").strip(),
            "power_name": str(self.power_var.get() or "").strip(),
            "power_states": {
                key: bool(variable.get())
                for key, variable in self.power_state_vars.items()
            },
            "reference_system": str(
                self.reference_system_var.get() or ""
            ).strip(),
            "max_distance_ly": str(self.max_distance_var.get() or "50").strip(),
        }

    def _save_last_filters_if_enabled(self):
        startup = self.v8_settings.get("startup", {})
        if bool(startup.get("remember_last_filters", False)):
            self.v8_settings["last_filters"] = self._capture_current_filters()
        app_settings.save_settings(self.v8_settings)

    def _on_v8_close(self):
        try:
            self._save_last_filters_if_enabled()
        finally:
            self.destroy()

    def _build_settings_button(self):
        self.settings_button = tk.Button(
            self._stage,
            text="Settings ⚙",
            command=self._open_settings_dialog,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            padx=8,
            pady=3,
            font=("Segoe UI", 9),
        )

        # Keep Settings flush-right and Reference Tables immediately to its left.
        self.settings_button.place(x=1245, y=20, width=95, height=30)
        reference_button = getattr(self, "reference_tables_button", None)
        if reference_button is not None:
            reference_button.place_configure(x=1065, y=20, width=170, height=30)

    def _open_settings_dialog(self):
        existing = getattr(self, "_settings_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return

        window = tk.Toplevel(self)
        # Keep the native window unmapped while the dialog is being built.
        # The final GUI layer explicitly reveals it only after all inherited
        # Settings extensions and theme controls are complete.
        window.withdraw()
        self._settings_window = window
        window.title("Settings")
        window.configure(bg=COLORS["bg"])
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()

        width, height = 600, 700
        self.update_idletasks()
        x = self.winfo_rootx() + max(20, (self.winfo_width() - width) // 2)
        y = self.winfo_rooty() + max(20, (self.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

        def layout_settings_content(logical_height):
            logical_width = ui_scale_runtime.logical_px(window.winfo_width())
            if logical_width <= 1:
                logical_width = 600
            compact_layout = logical_height < 660
            if compact_layout:
                startup_panel.place_configure(x=18, y=0, width=564, height=175)
                rhino_panel.place_configure(x=18, y=179, width=564, height=202)
                application_panel.place_configure(x=18, y=385, width=564, height=122)
                source_label.place_configure(y=28)
                path_entry.place_configure(y=25)
                browse_button.place_configure(y=25)
                auto_button.place_configure(y=25)
                status_label.place_configure(y=55, height=20)
                ask_sync_check.place_configure(y=78)
                commander_label.place_configure(y=104)
                api_commander_entry.place_configure(y=101)
                api_key_label.place_configure(y=133)
                api_key_entry.place_configure(y=130)
                rhino_help_label.place_configure(y=159, height=38)
            else:
                startup_panel.place_configure(x=18, y=18, width=564, height=185)
                rhino_panel.place_configure(x=18, y=209, width=564, height=270)
                application_panel.place_configure(x=18, y=484, width=564, height=124)
                source_label.place_configure(y=42)
                path_entry.place_configure(y=38)
                browse_button.place_configure(y=38)
                auto_button.place_configure(y=38)
                status_label.place_configure(y=77)
                ask_sync_check.place_configure(y=109)
                commander_label.place_configure(y=139)
                api_commander_entry.place_configure(y=135)
                api_key_label.place_configure(y=173)
                api_key_entry.place_configure(y=169)
                rhino_help_label.place_configure(y=207, height=45)

            action_y = logical_height - (29 if compact_layout else 43)
            if logical_width < 420:
                reset_x, reset_width = 8, 110
                cancel_x, cancel_width = logical_width - 158, 70
                save_x, save_width = logical_width - 88, 80
            else:
                reset_x, reset_width = 18, 120
                cancel_x, cancel_width = logical_width - 200, 80
                save_x, save_width = logical_width - 110, 92
            button_positions = {
                "Reset Defaults": (reset_x, action_y, reset_width),
                "Cancel": (cancel_x, action_y, cancel_width),
                "Save": (save_x, action_y, save_width),
            }
            for child in window.winfo_children():
                if isinstance(child, tk.Button):
                    position = button_positions.get(str(child.cget("text")))
                    if position is not None:
                        child.place_configure(
                            x=position[0], y=position[1], width=position[2]
                        )

        window._edhf_layout_settings_content = layout_settings_content

        startup = self.v8_settings.get("startup", {})
        rhino = self.v8_settings.get("rhinospotter", {})
        auto_rhino_path = str(app_settings.default_rhinospotter_data_path())
        saved_rhino_path = str(
            app_settings.resolve_rhinospotter_data_path(self.v8_settings)
        )

        hotspot_var = tk.BooleanVar(
            window, value=bool(startup.get("hotspots_enabled", True))
        )
        planets_var = tk.BooleanVar(
            window, value=bool(startup.get("planets_enabled", True))
        )
        community_var = tk.BooleanVar(
            window, value=bool(startup.get("community_deposits_enabled", True))
        )
        remember_var = tk.BooleanVar(
            window, value=bool(startup.get("remember_last_filters", False))
        )
        max_distance_var = tk.StringVar(
            window,
            value=self._format_distance(startup.get("max_distance_ly", 50.0)),
        )
        rhino_path_var = tk.StringVar(
            window,
            value=saved_rhino_path or auto_rhino_path,
        )
        ask_sync_var = tk.BooleanVar(
            window, value=bool(rhino.get("ask_before_sync", True))
        )
        community_api = self.v8_settings.get("community_api", {})
        api_commander_var = tk.StringVar(
            window, value=str(community_api.get("commander", "") or "")
        )
        api_key_var = tk.StringVar(window)
        rhino_status_var = tk.StringVar(window)

        def panel(y, height, title):
            frame = tk.Frame(window, bg=COLORS["panel"])
            frame.place(x=18, y=y, width=564, height=height)
            tk.Label(
                frame,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["orange"],
                font=("Segoe UI", 10, "bold"),
            ).place(x=12, y=9)
            return frame

        def check(parent, text, variable, x, y, width=260):
            widget = tk.Checkbutton(
                parent,
                text=text,
                variable=variable,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                activebackground=COLORS["panel"],
                activeforeground=COLORS["text"],
                selectcolor="#404040",
                highlightthickness=0,
                bd=0,
                anchor="w",
                font=("Segoe UI", 9),
            )
            widget.place(x=x, y=y, width=width, height=22)
            return widget

        startup_panel = panel(18, 185, "STARTUP DEFAULTS")
        check(startup_panel, "Hotspots enabled", hotspot_var, 12, 37)
        check(startup_panel, "Planets enabled", planets_var, 12, 64)
        check(
            startup_panel,
            "Community Deposits enabled",
            community_var,
            12,
            91,
        )
        check(
            startup_panel,
            "Remember last filters",
            remember_var,
            285,
            37,
        )

        tk.Label(
            startup_panel,
            text="Default Max LY",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).place(x=285, y=73)
        tk.Entry(
            startup_panel,
            textvariable=max_distance_var,
            bg="#3b3b3b",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 9),
        ).place(x=398, y=69, width=40, height=26)

        tk.Label(
            startup_panel,
            text=(
                "When Remember last filters is enabled, the latest Hotspots, "
                "Planets, Community and System Filter selections override these "
                "startup defaults on the next launch."
            ),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            anchor="w",
            wraplength=525,
            font=("Segoe UI", 8),
        ).place(x=12, y=137, width=530, height=38)

        rhino_panel = panel(209, 270, "COMMUNITY DEPOSITS")

        source_label = tk.Label(
            rhino_panel,
            text="Source",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        source_label.place(x=12, y=42)

        path_entry = tk.Entry(
            rhino_panel,
            textvariable=rhino_path_var,
            bg="#3b3b3b",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
        )
        path_entry.place(x=82, y=38, width=325, height=27)

        browse_button = tk.Button(
            rhino_panel,
            text="Browse...",
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
        )
        browse_button.place(x=417, y=38, width=65, height=27)

        auto_button = tk.Button(
            rhino_panel,
            text="Auto",
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 8),
        )
        auto_button.place(x=489, y=38, width=55, height=27)

        status_label = tk.Label(
            rhino_panel,
            textvariable=rhino_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            anchor="w",
            font=("Segoe UI", 9),
        )
        status_label.place(x=12, y=77, width=532, height=24)

        ask_sync_check = check(
            rhino_panel,
            "Ask before exporting bookmarks to Community Deposits",
            ask_sync_var,
            12,
            109,
            width=360,
        )

        commander_label = tk.Label(rhino_panel, text="Commander", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Segoe UI", 9))
        commander_label.place(x=12, y=139)
        api_commander_entry = tk.Entry(rhino_panel, textvariable=api_commander_var, bg="#3b3b3b",
                 fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat",
                 font=("Segoe UI", 9))
        api_commander_entry.place(x=92, y=135, width=180, height=25)
        api_key_label = tk.Label(rhino_panel, text="API Key", bg=COLORS["panel"], fg=COLORS["muted"],
                                 font=("Segoe UI", 9))
        api_key_label.place(x=12, y=173)
        api_key_entry = tk.Entry(rhino_panel, textvariable=api_key_var, bg="#3b3b3b",
                                 fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat",
                                 font=("Segoe UI", 9))
        api_key_entry.place(x=82, y=169, width=400, height=25)

        rhino_help_label = tk.Label(
            rhino_panel,
            text=(
                "One key with can_read=1 and can_write=1 is stored in shared "
                "Windows Credential Manager; blank keeps the saved key. "
                "Auto prefers RhinoSpotter 5.1+ rs_api, with SQLite/JSON fallbacks."
            ),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            anchor="w",
            wraplength=525,
            font=("Segoe UI", 8),
        )
        rhino_help_label.place(x=12, y=207, width=530, height=45)

        def refresh_rhino_status(_event=None):
            text = str(rhino_path_var.get() or "").strip()
            source = Path(text).expanduser() if text else Path(auto_rhino_path)
            try:
                info = rhinospotter_sync_service.inspect_source(source)
            except Exception:
                rhino_status_var.set("RhinoSpotter data source not detected")
                status_label.configure(fg=COLORS["red"])
                return

            source_type = info.get("source_type")
            if source_type == "rs_api":
                version = str(info.get("api_version") or "").strip()
                source_label = (
                    f"RhinoSpotter API {version}" if version else "RhinoSpotter API"
                )
            elif source_type == "sqlite":
                source_label = "SQLite fallback"
            else:
                source_label = "Legacy JSON cards"

            records_found = int(info.get("records_found", 0) or 0)
            rhino_status_var.set(
                f"{source_label} detected · {records_found} bookmarks"
            )
            status_label.configure(fg=COLORS["green"])

        def browse_rhino():
            current_text = str(rhino_path_var.get() or "").strip()
            current = Path(current_text).expanduser() if current_text else Path(auto_rhino_path)
            if current.is_dir():
                initial = current
            elif current.parent.is_dir():
                initial = current.parent
            else:
                initial = Path(auto_rhino_path).parent

            selected = filedialog.askdirectory(
                parent=window,
                title="Select RhinoSpotter data folder",
                initialdir=str(initial),
            )
            if selected:
                rhino_path_var.set(selected)
                refresh_rhino_status()

        def use_auto_rhino():
            rhino_path_var.set(auto_rhino_path)
            refresh_rhino_status()

        browse_button.configure(command=browse_rhino, state="normal")
        auto_button.configure(command=use_auto_rhino, state="normal")
        path_entry.bind("<KeyRelease>", refresh_rhino_status, add="+")
        path_entry.bind("<FocusOut>", refresh_rhino_status, add="+")
        refresh_rhino_status()

        application_panel = panel(484, 124, "APPLICATION")
        update_check = tk.Checkbutton(
            application_panel,
            text="Check for updates on startup",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["panel"],
            activeforeground=COLORS["text"],
            selectcolor="#404040",
            state="normal",
            anchor="w",
            font=("Segoe UI", 9),
        )
        update_check.place(x=12, y=34, width=480, height=20)

        def reset_dialog_defaults():
            hotspot_var.set(True)
            planets_var.set(True)
            community_var.set(True)
            max_distance_var.set("50")
            remember_var.set(False)
            rhino_path_var.set(auto_rhino_path)
            ask_sync_var.set(True)
            api_commander_var.set("")
            api_key_var.set("")
            refresh_rhino_status()

        def restore_dialog_values():
            current_startup = self.v8_settings.get("startup", {})
            current_rhino = self.v8_settings.get("rhinospotter", {})

            hotspot_var.set(bool(current_startup.get("hotspots_enabled", True)))
            planets_var.set(bool(current_startup.get("planets_enabled", True)))
            community_var.set(
                bool(current_startup.get("community_deposits_enabled", True))
            )
            remember_var.set(
                bool(current_startup.get("remember_last_filters", False))
            )
            max_distance_var.set(
                self._format_distance(current_startup.get("max_distance_ly", 50.0))
            )

            current_path = str(
                app_settings.resolve_rhinospotter_data_path(self.v8_settings)
            )
            rhino_path_var.set(current_path)
            ask_sync_var.set(bool(current_rhino.get("ask_before_sync", True)))
            api_commander_var.set(str(
                self.v8_settings.get("community_api", {}).get("commander", "") or ""
            ))
            api_key_var.set("")
            refresh_rhino_status()

        window._edhf_restore_settings_values = restore_dialog_values

        def close_dialog():
            # Persistent final Settings windows are hidden rather than destroyed.
            # Restore every staged value first so Cancel/X still behaves normally.
            for callback_name in (
                "_edhf_restore_settings_values",
                "_edhf_restore_application_values",
            ):
                callback = getattr(window, callback_name, None)
                if callable(callback):
                    try:
                        callback()
                    except (AttributeError, tk.TclError):
                        pass
            api_key_var.set("")

            hide = getattr(self, "_hide_persistent_settings_window", None)
            if callable(hide):
                hide(window)
                return

            self._settings_window = None
            window.destroy()

        def save_dialog_settings():
            try:
                max_distance = float(str(max_distance_var.get()).strip())
                if max_distance <= 0 or max_distance > 300:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    APP_TITLE,
                    "Default Max LY must be a number between 1 and 300.",
                    parent=window,
                )
                return

            entered_rhino_path = str(rhino_path_var.get() or "").strip()
            if (
                not entered_rhino_path
                or self._path_key(entered_rhino_path)
                == self._path_key(auto_rhino_path)
            ):
                stored_rhino_path = ""
            else:
                stored_rhino_path = entered_rhino_path

            self.v8_settings["startup"] = {
                "hotspots_enabled": bool(hotspot_var.get()),
                "planets_enabled": bool(planets_var.get()),
                "community_deposits_enabled": bool(community_var.get()),
                "max_distance_ly": max_distance,
                "remember_last_filters": bool(remember_var.get()),
            }
            self.v8_settings["rhinospotter"] = {
                "data_path": stored_rhino_path,
                "ask_before_sync": bool(ask_sync_var.get()),
            }
            commander = str(api_commander_var.get() or "").strip()
            self.v8_settings["community_api"] = {"commander": commander}
            if remember_var.get():
                self.v8_settings["last_filters"] = self._capture_current_filters()

            try:
                from edmc_plugin.EDHF_Community_Navigator.api_credentials import store_api_key

                if api_key_var.get():
                    store_api_key(commander, api_key_var.get())
                app_settings.save_settings(self.v8_settings)
            except (OSError, ValueError) as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=window)
                return
            api_key_var.set("")

            self._refresh_runtime_settings()
            self.status_var.set("Settings saved")
            close_dialog()

        tk.Button(
            window,
            text="Reset Defaults",
            command=reset_dialog_defaults,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 9),
        ).place(x=18, y=657, width=120, height=28)

        tk.Button(
            window,
            text="Cancel",
            command=close_dialog,
            bg="#3a4148",
            fg=COLORS["text"],
            activebackground="#46515c",
            activeforeground=COLORS["text"],
            relief="flat",
            font=("Segoe UI", 9),
        ).place(x=400, y=657, width=80, height=28)

        tk.Button(
            window,
            text="Save",
            command=save_dialog_settings,
            bg=COLORS["orange"],
            fg="#111111",
            activebackground="#ffb52e",
            activeforeground="#111111",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        ).place(x=490, y=657, width=92, height=28)

        layout_settings_content(height)

        window.protocol("WM_DELETE_WINDOW", close_dialog)

        # Standalone/intermediate GUI classes can still use this mixin directly.
        # The concrete final app sets _defer_settings_reveal while it adds its
        # extra controls, so only that layer decides when the window is ready.
        if not getattr(self, "_defer_settings_reveal", False):
            window.update_idletasks()
            window.deiconify()
            window.lift()
            window.focus_force()

    def start_rhino_upload(self):
        return super().start_rhino_upload()

    def _rhino_sync_preview(self):
        data_path = app_settings.resolve_rhinospotter_data_path(
            self.v8_settings
        )
        return rhinospotter_sync_service.preview_sync(data_path=data_path)

    def _rhino_upload_worker(self, systems, refresh_after_upload, expected_snapshot):
        try:
            data_path = app_settings.resolve_rhinospotter_data_path(
                self.v8_settings
            )
            summary = rhinospotter_sync_service.confirm_sync(
                data_path=data_path, expected_snapshot=expected_snapshot
            )
            if summary.get("stale"):
                self.after(
                    0, self._rhino_preview_ready, summary["plan"],
                    systems, refresh_after_upload,
                )
                return

            community_headers = []
            community_rows = []
            if refresh_after_upload:
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
