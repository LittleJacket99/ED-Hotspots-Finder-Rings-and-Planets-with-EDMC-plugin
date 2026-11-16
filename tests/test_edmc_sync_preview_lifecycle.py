import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PLUGIN_ROOT = str(Path(__file__).resolve().parents[1] / "edmc_plugin")
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)


class _Control:
    def __init__(self):
        self.options = {}

    def config(self, **kwargs):
        self.options.update(kwargs)


class _Parent:
    pass


class _Frame:
    def __init__(self, parent):
        self.parent = parent

    def winfo_toplevel(self):
        return self.parent


def _module(name, **attributes):
    result = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    return result


class EdmcSyncPreviewLifecycleTests(unittest.TestCase):
    def _load_plugin_module(self):
        class RhinoSpotterNotInstalled(Exception):
            pass

        stubs = {
            "config": _module(
                "config", appname="EDMarketConnector",
                config=types.SimpleNamespace(shutting_down=False),
            ),
            "theme": _module("theme", theme=types.SimpleNamespace(update=Mock())),
            "EDHF_Community_Navigator.community_api": _module(
                "EDHF_Community_Navigator.community_api",
                fetch_system_deposits=Mock(),
            ),
            "EDHF_Community_Navigator.api_credentials": _module(
                "EDHF_Community_Navigator.api_credentials", store_api_key=Mock()
            ),
            "EDHF_Community_Navigator.navigator": _module(
                "EDHF_Community_Navigator.navigator",
                NavigatorOverlay=type("NavigatorOverlay", (), {}),
            ),
            "EDHF_Community_Navigator.results_window": _module(
                "EDHF_Community_Navigator.results_window",
                DepositsWindow=type("DepositsWindow", (), {}),
                theme_colours=lambda: {
                    "background": "#202020", "foreground": "#f0f0f0",
                    "muted": "#888888", "selected_bg": "#dddddd",
                    "border": "#777777", "font_family": "Segoe UI",
                },
            ),
            "EDHF_Community_Navigator.update_checker": _module(
                "EDHF_Community_Navigator.update_checker", check_for_update=Mock()
            ),
            "EDHF_Community_Navigator.rhinospotter_client": _module(
                "EDHF_Community_Navigator.rhinospotter_client",
                RhinoSpotterNotInstalled=RhinoSpotterNotInstalled,
                confirm_sync=Mock(), preview_sync=Mock(),
            ),
        }
        module_name = "EDHF_Community_Navigator.load"
        names = [*stubs, module_name]
        previous = {name: sys.modules.get(name) for name in names}
        sys.modules.update(stubs)
        sys.modules.pop(module_name, None)
        try:
            return importlib.import_module(module_name), previous, names
        except Exception:
            for name in names:
                sys.modules.pop(name, None)
                if previous[name] is not None:
                    sys.modules[name] = previous[name]
            raise

    def _with_plugin(self):
        module, previous, names = self._load_plugin_module()
        self.addCleanup(self._restore_modules, module, previous, names)
        return module

    @staticmethod
    def _restore_modules(module, previous, names):
        for name in names:
            sys.modules.pop(name, None)
            if previous[name] is not None:
                sys.modules[name] = previous[name]

    def _ready_plugin(self, module):
        parent = _Parent()
        module._frame = _Frame(parent)
        module._current_commander = "CMDR"
        module._sync_button = _Control()
        module._scan_button = _Control()
        module._status = _Control()
        module._update_scan_button_state = Mock()
        return parent

    def test_cancel_passes_dialog_window_and_edmc_parent_to_centering_callback(self):
        module = self._with_plugin()
        parent = self._ready_plugin(module)
        dialog_window = object()

        def show(_parent, _plan, *, apply_theme, position_window,
                 palette, button_factory, message_factory):
            self.assertIsNotNone(apply_theme)
            self.assertEqual(palette["font_family"], "Segoe UI")
            self.assertIs(button_factory, module.ttk.Button)
            self.assertIs(message_factory, module.MessageLabel)
            position_window(dialog_window)
            return False

        with patch.object(module, "show_sync_preview", side_effect=show), patch.object(
            module, "_center_credentials_window"
        ) as center:
            module._handle_sync_preview(("CMDR", {"new": 1, "modified": 0}))

        center.assert_called_once_with(dialog_window, parent)
        self.assertEqual(module._sync_button.options["state"], module.tk.NORMAL)
        self.assertEqual(module._scan_button.options["state"], module.tk.NORMAL)
        module._update_scan_button_state.assert_called_once()

    def test_each_preview_uses_the_current_edmc_theme_palette(self):
        module = self._with_plugin()
        self._ready_plugin(module)
        palettes = [
            {"background": "#101010", "foreground": "#ffffff"},
            {"background": "#eeeeee", "foreground": "#111111"},
        ]
        with patch.object(module, "theme_colours", side_effect=palettes), patch.object(
            module, "show_sync_preview", return_value=False
        ) as show:
            module._handle_sync_preview(("CMDR", {"new": 1}))
            module._handle_sync_preview(("CMDR", {"new": 1}))

        self.assertEqual(
            [call.kwargs["palette"] for call in show.call_args_list], palettes
        )
        self.assertTrue(all(
            call.kwargs["button_factory"] is module.ttk.Button
            for call in show.call_args_list
        ))

    def test_dialog_failure_logs_traceback_and_restores_sync_and_scan(self):
        module = self._with_plugin()
        self._ready_plugin(module)
        expected = TypeError("synthetic dialog failure")

        with patch.object(module, "show_sync_preview", side_effect=expected):
            with self.assertLogs(module.logger, level="ERROR") as captured:
                module._handle_sync_preview(("CMDR", {"new": 1, "modified": 0}))

        self.assertTrue(any("Traceback (most recent call last)" in line for line in captured.output))
        self.assertTrue(any("TypeError: synthetic dialog failure" in line for line in captured.output))
        self.assertEqual(module._status.options["text"], "Sync preview unavailable")
        self.assertEqual(module._sync_button.options["state"], module.tk.NORMAL)
        self.assertEqual(module._scan_button.options["state"], module.tk.NORMAL)
        module._update_scan_button_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
