"""Finder-only settings and native resize tests, with temporary config and no HTTP."""
import copy
from itertools import product
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch

import app_settings
import community_deposits
import finder_distance
import local_scan
import system_filter_search
import ui_scale_runtime
import hotspots_finder_gui_v8_final as final_gui

ROOT = Path(__file__).resolve().parents[1]


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DistancePolicyTests(unittest.TestCase):
    def test_regular_system_loading_still_follows_pages_without_load_all_action(self):
        from unittest.mock import Mock
        session = Mock()
        payloads = [dict(status="ok", deposits=[], next_cursor="second-page"),
                    dict(status="ok", deposits=[], next_cursor=None)]
        session.get.side_effect = [SimpleNamespace(status_code=200, json=lambda p=p: p) for p in payloads]
        with patch.object(community_deposits, "_read_api_key", return_value="synthetic"):
            community_deposits.fetch_system_deposits("Synthetic System", session=session, commander="Synthetic")
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args_list[0].kwargs["params"], dict(system="Synthetic System"))
        self.assertEqual(session.get.call_args_list[1].kwargs["params"], dict(system="Synthetic System", cursor="second-page"))

    def test_effective_filter_validation_and_finite_values(self):
        for value in ("100", 100, 0.5, "2,5"):
            expected = float(str(value).replace(",", "."))
            self.assertEqual(system_filter_search._validate_max_distance(value), expected)
            self.assertEqual(local_scan.normalize_config(dict(reference_system="Sol", max_distance_ly=value))["max_distance_ly"], expected)
        for value in (101, 300, 0, -1, None, True, "bad", "NaN", "Infinity", float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    finder_distance.validate_max_distance(value)
        for value in (101, "NaN", "Infinity", -1):
            with self.assertRaises(local_scan.LocalScanError):
                local_scan.normalize_config(dict(reference_system="Sol", max_distance_ly=value))

    def test_old_config_normalized_without_write_and_unrelated_values_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "config.json"
            with patch.object(app_settings, "APP_DATA_DIR", Path(directory)), patch.object(app_settings, "CONFIG_PATH", path):
                for value, expected in ((300, 100), (-1, 50), ("bad", 50), ("NaN", 50), (True, 50), (30, 30)):
                    path.write_text(__import__("json").dumps(dict(unrelated="keep", v8_settings=dict(startup=dict(max_distance_ly=value)))), encoding="utf-8")
                    original = path.read_bytes()
                    loaded = app_settings.load_settings()
                    self.assertEqual(loaded["startup"]["max_distance_ly"], expected)
                    self.assertEqual(path.read_bytes(), original)
                    app_settings.save_settings(loaded)
                    self.assertEqual(app_settings.load_settings()["startup"]["max_distance_ly"], expected)
                    self.assertEqual(__import__("json").loads(path.read_text())["unrelated"], "keep")


class FinderGuiSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.original_streams = sys.stdout, sys.stderr
        self.manager_methods = [(cls, name, getattr(cls, name)) for cls, names in
                                ((tk.Place, ("place", "place_configure")),
                                 (tk.Pack, ("pack", "pack_configure")),
                                 (tk.Grid, ("grid", "grid_configure"))) for name in names]
        self.scaling_state = ui_scale_runtime._SCALE, ui_scale_runtime._INSTALLED
        self.patches = [patch.object(app_settings, "APP_DATA_DIR", Path(self.temp.name)),
                        patch.object(app_settings, "CONFIG_PATH", Path(self.temp.name) / "config.json"),
                        patch("rhinospotter_sync_service.inspect_source", side_effect=ValueError("synthetic source")),
                        patch.object(final_gui.FinderV8FinalApp, "_apply_app_icon"),
                        patch("requests.sessions.Session.request", side_effect=AssertionError("No HTTP allowed")),
                        patch("hotspots_finder_gui_v8_settings.messagebox.showerror")]
        self.mocks = [p.start() for p in self.patches]
        self.apps = []

    def tearDown(self):
        for app in reversed(self.apps):
            self.destroy_app(app)
        sys.stdout, sys.stderr = self.original_streams
        for patcher in reversed(self.patches):
            patcher.stop()
        for cls, name, method in self.manager_methods:
            setattr(cls, name, method)
        ui_scale_runtime._SCALE, ui_scale_runtime._INSTALLED = self.scaling_state
        self.temp.cleanup()

    def destroy_app(self, app):
        try:
            if app.winfo_exists():
                app.update_idletasks()
                for timer in app.tk.call("after", "info"):
                    app.tk.call("after", "cancel", timer)
                app.destroy()
        except tk.TclError:
            pass
        sys.stdout, sys.stderr = self.original_streams

    def create_app(self, *, distance=30, remember=False, theme="deep_black", scale=1.0, keep_saved=False):
        if not keep_saved:
            saved = copy.deepcopy(app_settings.DEFAULT_SETTINGS)
            saved["startup"].update(max_distance_ly=distance, remember_last_filters=remember)
            saved["last_filters"] = dict(max_distance_ly="80", reference_system="Remembered system") if remember else {}
            saved["application"].update(theme=theme, ui_scale=scale, check_updates_on_startup=False)
            app_settings.save_settings(saved)
        app = final_gui.FinderV8FinalApp()
        self.apps.append(app)
        app.attributes("-alpha", 1)
        app.deiconify()
        app.update()
        return app

    def default_entry(self, app):
        window = app._settings_window
        label = next(w for w in descendants(window) if isinstance(w, tk.Label) and w.cget("text") == "Default Max LY")
        return next(w for w in label.master.winfo_children() if isinstance(w, tk.Entry))

    def save(self, app):
        next(w for w in app._settings_window.winfo_children() if isinstance(w, tk.Button) and w.cget("text") == "Save").invoke()
        app.update()

    def test_setting_updates_filter_live_manual_filter_does_not_replace_default_and_restart(self):
        app = self.create_app(remember=True)
        self.assertEqual(app.max_distance_var.get(), "30")
        self.assertEqual(app.reference_system_var.get(), "Remembered system")
        app.max_distance_var.set("70")
        self.assertEqual(app_settings.load_settings()["startup"]["max_distance_ly"], 30)
        entry = self.default_entry(app)
        entry.delete(0, "end")
        entry.insert(0, "45")
        self.save(app)
        self.assertEqual(app.max_distance_var.get(), "45")
        app.max_distance_var.set("80")
        app._open_settings_dialog()
        self.save(app)  # Unchanged default must not overwrite this session's manual filter.
        self.assertEqual(app.max_distance_var.get(), "80")
        self.assertEqual(app_settings.load_settings()["startup"]["max_distance_ly"], 45)
        self.destroy_app(app)
        restarted = self.create_app(keep_saved=True)
        self.assertEqual(restarted.max_distance_var.get(), "45")

    def test_invalid_settings_are_rejected_and_old_large_values_start_safely(self):
        app = self.create_app(distance=250)
        self.assertEqual(app.max_distance_var.get(), "100")
        entry = self.default_entry(app)
        for text in ("101", "NaN", "Infinity", "-1"):
            entry.delete(0, "end")
            entry.insert(0, text)
            self.save(app)
            self.assertEqual(app.max_distance_var.get(), "100")
        self.assertEqual(self.mocks[-1].call_count, 4)

    def test_sections_credits_and_repository_link_in_both_themes(self):
        for theme in ("deep_black", "green_warm"):
            app = self.create_app(theme=theme)
            texts = [w.cget("text") for w in descendants(app) if isinstance(w, (tk.Label, tk.Button, tk.Checkbutton))]
            self.assertIn("Alliance Community Deposits", texts)
            self.assertIn("max 100 Ly", texts)
            self.assertIn("Developed by CMDR LittleJacket", texts)
            self.assertFalse(any("Load All" in text for text in texts))
            self.assertFalse(hasattr(type(app), "start_load_all_deposits"))
            link = next(w for w in descendants(app._settings_window) if isinstance(w, tk.Label) and w.cget("text") == "GitHub Repository")
            credit = next(w for w in descendants(app._settings_window) if isinstance(w, tk.Label) and w.cget("text") == "Developed by CMDR LittleJacket")
            self.assertEqual(credit.cget("bg"), final_gui.visual_theme.THEMES[theme]["panel"])
            for label in (credit, link):
                self.assertLessEqual(label.winfo_reqwidth(), label.winfo_width())
            with patch.object(final_gui.ui_theme.webbrowser, "open_new_tab") as browser:
                link.event_generate("<Button-1>")
                browser.assert_called_once_with("https://github.com/LittleJacket99/ED-Hotspots-Finder-Rings-and-Planets-with-EDMC-plugin")
            self.assertLessEqual(link.winfo_x() + link.winfo_width(), link.master.winfo_width())
            self.destroy_app(app)

    def test_native_resize_keeps_filter_geometry_and_scrolling_and_expand(self):
        for theme, scale in product(("deep_black", "green_warm"), (1.0, 1.15, 1.25)):
            app = self.create_app(theme=theme, scale=scale)
            initial = app.winfo_width(), app.winfo_height()
            self.assertEqual(initial, (round(1359 * scale), round(819 * scale)))
            self.assertTrue(all(app.resizable()))
            self.assertEqual(app.minsize(), (round(initial[0] / 2), initial[1]))
            filters = {name: (getattr(app, name).winfo_x(), getattr(app, name).winfo_y(),
                              getattr(app, name).winfo_width(), getattr(app, name).winfo_height()) for name in
                       ("_hotspots_box", "_planets_box", "_community_box", "_systems_panel", "_power_states_box", "_reference_box", "_distance_box")}
            app.status_var.set("Long status message " * 20)
            app.geometry(f"{app.minsize()[0]}x{initial[1]}")
            app.update()
            app._apply_responsive_layout()
            app.update()
            self.assertLess(app._results_panel.winfo_width(), round(200 * scale))
            self.assertEqual(filters, {name: (getattr(app, name).winfo_x(), getattr(app, name).winfo_y(),
                                              getattr(app, name).winfo_width(), getattr(app, name).winfo_height()) for name in filters})
            for widget in (app.scan_button, app.stop_button, app.log_details_button):
                self.assertGreater(widget.winfo_width(), 1)
                self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), app._bottom_bar.winfo_width())
            self.assertGreaterEqual(app.expand_results_button.winfo_x(), 0)
            self.assertLessEqual(app._power_states_box.winfo_y() + app._power_states_box.winfo_height(), app._bottom_bar.winfo_y())
            for tree in (app.hotspot_tree, app.planet_tree, app.community_tree, app.systems_result_tree):
                app.notebook.select(tree.master.master)
                app._populate_tree(tree, ["System", "Body"], [dict(System="Synthetic system " * 8, Body="Synthetic body " * 8)])
                app.update()
                self.assertLess(tree.xview()[1], 1)
                tree.xview_moveto(1)
                self.assertGreater(tree.xview()[0], 0)
            narrow = app._results_panel.winfo_width()
            app._toggle_results_expansion()
            app.update()
            app._apply_responsive_layout()
            app.update()
            self.assertGreater(app._results_panel.winfo_width(), narrow)
            app._results_transition_pending = False
            app._toggle_results_expansion()
            app.update()
            app._apply_responsive_layout()
            app.update()
            self.assertEqual(app._results_panel.winfo_width(), narrow)
            app.geometry(f"{initial[0] + 80}x{initial[1] + 80}")
            app.update()
            app._apply_responsive_layout()
            app.update()
            self.assertGreater(app._results_panel.winfo_width(), narrow)
            self.destroy_app(app)


if __name__ == "__main__":
    unittest.main()
