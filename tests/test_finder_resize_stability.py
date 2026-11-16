"""Finder resize regression: real Tk geometry, synthetic config and no HTTP."""
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import test_finder_final_settings as finder_fixture
from test_finder_final_settings import descendants


class FinderResizeStabilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = finder_fixture.FinderGuiSettingsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def pump(self, app, seconds=0.08):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.update()
            time.sleep(0.005)

    def test_gradual_resize_preserves_widgets_filters_opacity_and_native_geometry(self):
        for theme in ("deep_black", "green_warm"):
            for scale in (1.0, 1.15):
                app = self.fixture.create_app(theme=theme, scale=scale)
                app._restore_guard_enabled = True
                widgets = set(descendants(app))
                filters = [getattr(app, name) for name in ("_hotspots_box", "_planets_box", "_community_box",
                           "_systems_panel", "_reference_box", "_distance_box", "_power_states_box")]
                positions = [w.place_info() for w in filters]
                with patch.object(app, "geometry", side_effect=AssertionError("No app geometry during resize")), \
                        patch.object(app, "_apply_scaled_root_geometry", side_effect=AssertionError("No recenter")), \
                        patch.object(app, "_sync_results_outline", wraps=app._sync_results_outline) as outline:
                    for index, width in enumerate((1359, 1200, 1000, 850, 680, 850, 1000, 1200, 1359)):
                        app.tk.call("wm", "geometry", app._w, f"{round(width * scale)}x{round(819 * scale)}")
                        app.notebook.select(app.notebook.tabs()[index % len(app.notebook.tabs())])
                        app.update()
                        self.assertEqual(app._stage.winfo_width(), app.winfo_width())
                        self.assertTrue(all(w.winfo_ismapped() for w in filters))
                        self.assertEqual([w.place_info() for w in filters], positions)
                        self.assertFalse(app._results_expanded)
                        self.assertEqual(float(app.attributes("-alpha")), 1)
                        self.assertEqual(set(descendants(app)), widgets)
                    calls = outline.call_count
                    self.pump(app, 0.12)
                    self.assertLessEqual(outline.call_count - calls, 1)  # settles, no Configure feedback loop
                    app._toggle_results_expansion()
                    self.pump(app)
                    self.assertTrue(app._results_expanded)
                    self.assertFalse(any(w.winfo_ismapped() for w in filters))
                    for width in (1000, 680, 1359):
                        app.tk.call("wm", "geometry", app._w, f"{round(width * scale)}x{round(819 * scale)}")
                        app.update()
                        self.assertTrue(app._results_expanded)
                        self.assertFalse(any(w.winfo_ismapped() for w in filters))
                    app._toggle_results_expansion()
                    self.pump(app)
                    self.assertFalse(app._results_expanded)
                    self.assertTrue(all(w.winfo_ismapped() for w in filters))
                    self.assertEqual([w.place_info() for w in filters], positions)
                    self.assertEqual(set(descendants(app)), widgets)
                self.fixture.destroy_app(app)

    def test_settings_application_rows_do_not_overlap_and_keep_theme_controls(self):
        for theme in ("deep_black", "green_warm"):
            for scale in (1.0, 1.15):
                app = self.fixture.create_app(theme=theme, scale=scale)
                window = app._settings_window
                credit = next(w for w in descendants(window) if isinstance(w, tk.Label)
                              and w.cget("text") == "Developed by CMDR LittleJacket")
                link = next(w for w in descendants(window) if isinstance(w, tk.Label)
                            and w.cget("text") == "GitHub Repository")
                panel = credit.master
                check = next(w for w in panel.winfo_children() if isinstance(w, tk.Checkbutton)
                             and w.cget("text") == "Check for updates on startup")
                combos = [w for w in panel.winfo_children() if w.winfo_class() == "TCombobox"]
                self.assertEqual(len(combos), 2)
                self.assertEqual(sorted(w.winfo_y() for w in combos), [round(34 * scale)] * 2)
                self.assertGreater(check.winfo_y(), max(w.winfo_y() + w.winfo_height() for w in combos))
                self.assertLess(check.winfo_y() - max(w.winfo_y() + w.winfo_height() for w in combos), round(12 * scale))
                self.assertEqual(credit.winfo_y(), link.winfo_y())
                self.assertGreaterEqual(credit.winfo_y(), check.winfo_y() + check.winfo_height())
                self.assertGreater(link.winfo_x(), credit.winfo_x() + credit.winfo_width())
                for widget in (credit, link, check):
                    self.assertLessEqual(widget.winfo_y() + widget.winfo_height(), panel.winfo_height())
                    self.assertLessEqual(widget.winfo_reqwidth(), widget.winfo_width())
                self.fixture.destroy_app(app)

    @unittest.skipUnless(sys.platform == "win32", "Windows native maximize/restore")
    def test_native_windows_maximize_restore_in_dpi_aware_process(self):
        # DPI awareness must be enabled before the first Tk, exactly as main().
        # Use a child process to avoid changing the test runner's DPI context.
        code = r'''
import sys,time,ctypes
from ctypes import wintypes
from unittest.mock import patch
sys.path.insert(0,'tests')
import hotspots_finder_gui_v8_final as gui
gui._enable_windows_dpi_awareness()
from test_finder_final_settings import FinderGuiSettingsTests
case=FinderGuiSettingsTests();case.setUp()
def pump(app):
    end=time.monotonic()+0.15
    while time.monotonic()<end:app.update();time.sleep(0.005)
class MonitorInfo(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
user32=ctypes.windll.user32
user32.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD]
user32.MonitorFromWindow.restype=wintypes.HANDLE
user32.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.c_void_p]
user32.GetMonitorInfoW.restype=wintypes.BOOL
try:
    for scale,theme in ((1.0,'deep_black'),(1.15,'green_warm')):
        app=case.create_app(scale=scale,theme=theme);app._restore_guard_enabled=True
        app.tk.call('wm','geometry',app._w,f'{round(1000*scale)}x{round(819*scale)}+32+24');pump(app)
        original=app.tk.call('wm','geometry',app._w)
        with patch.object(app,'geometry',side_effect=AssertionError('No app reposition')),patch.object(app,'_apply_scaled_root_geometry',side_effect=AssertionError('No recenter')):
            app.state('zoomed');pump(app)
            assert app.state()=='zoomed'
            assert float(app.attributes('-alpha'))==1
            assert app._stage.winfo_width()==app.winfo_width()
            assert app._stage.winfo_height()==app.winfo_height()
            monitor=user32.MonitorFromWindow(app.winfo_id(),2)
            info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
            assert user32.GetMonitorInfoW(monitor,ctypes.byref(info))
            assert app.winfo_rooty()+app.winfo_height()<=info.rcWork.bottom+1, 'Client overlaps taskbar/work area'
            assert app.winfo_rootx()+app.winfo_width()<=info.rcWork.right+1
            app.state('normal');pump(app)
            assert app.tk.call('wm','geometry',app._w)==original, (original,app.tk.call('wm','geometry',app._w))
            assert float(app.attributes('-alpha'))==1
            app.iconify();pump(app)
            app.deiconify();pump(app)
            assert app.tk.call('wm','geometry',app._w)==original
            assert float(app.attributes('-alpha'))==1
        case.destroy_app(app)
    print('Native DPI-aware maximize/restore and monitor work area: PASS')
finally:case.tearDown()
'''
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
