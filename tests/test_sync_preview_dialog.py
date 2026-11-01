import unittest
from unittest.mock import patch

from edmc_plugin.EDHF_Community_Navigator import sync_preview_dialog as dialog


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.text = kwargs.get("text", "")
        self.command = kwargs.get("command")

    def grid(self, *args, **kwargs): pass
    def pack(self, *args, **kwargs): pass
    def configure(self, *args, **kwargs): self.kwargs.update(kwargs)
    config = configure
    def rowconfigure(self, *args, **kwargs): pass
    def columnconfigure(self, *args, **kwargs): pass
    def destroy(self): self.destroyed = True


class FakeWindow(FakeWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.protocols = {}
        self.geometry_history = []
        self.withdrawn = False
        self.visible = False
        parent.window = self

    def title(self, value): self.title_value = value
    def transient(self, *args): self.transient_args = args
    def resizable(self, *args): pass
    def update_idletasks(self): pass
    def winfo_screenwidth(self): return 1920
    def winfo_screenheight(self): return 1080
    def winfo_reqwidth(self): return 430
    def winfo_reqheight(self): return 250
    def geometry(self, value):
        self.geometry_value = value
        self.geometry_history.append((value, self.visible))
    def withdraw(self): self.withdrawn = True
    def deiconify(self): self.visible = True
    def winfo_exists(self): return not getattr(self, "destroyed", False)
    def grab_set(self): self.parent.current_grab = self
    def grab_release(self):
        if self.parent.current_grab is self:
            self.parent.current_grab = None
    def lift(self): pass
    def focus_force(self): pass
    def protocol(self, name, callback): self.protocols[name] = callback


class FakeParent:
    def __init__(self, action):
        self.action = action
        self.window = None
        self.current_grab = None

    def cget(self, key): return "#202020"
    def winfo_toplevel(self): return self
    def winfo_rootx(self): return 100
    def winfo_rooty(self): return 100
    def winfo_width(self): return 900
    def winfo_height(self): return 700
    def state(self): return "normal"
    def winfo_ismapped(self): return True

    def wait_window(self, _window):
        if self.action == "close":
            self.window.protocols["WM_DELETE_WINDOW"]()
            return
        target = "Confirm Sync" if self.action == "confirm" else "Cancel"
        for widget in _widgets:
            if widget.text == target and widget.command:
                if widget.kwargs.get("state") == dialog.tk.DISABLED:
                    return
                widget.command()
                return
        raise AssertionError(f"Missing {target} button")


_widgets = []


def _factory(*args, **kwargs):
    widget = FakeWidget(*args, **kwargs)
    _widgets.append(widget)
    return widget


class SyncPreviewDialogTests(unittest.TestCase):
    def _show(
        self, action, plan=None, parent_state="normal", position_window=None,
        apply_theme=None, button_factory=None, palette=None,
    ):
        _widgets.clear()
        parent = FakeParent(action)
        parent.state = lambda: parent_state
        plan = plan or {
            "source_type": "rs_api", "source_path": "test/rs_api.py",
            "commander": "CMDR", "records_found": 0, "records_valid": 0,
            "invalid": 0, "commander_mismatches": 0, "skipped": 0,
            "credential_missing": 0, "new": 0, "modified": 0,
            "unchanged": 0, "pending": [], "preview_pending": [],
        }
        with patch.object(dialog.tk, "Toplevel", side_effect=FakeWindow), \
                patch.object(dialog.tk, "Frame", side_effect=_factory), \
                patch.object(dialog.tk, "Label", side_effect=_factory), \
                patch.object(dialog.tk, "Button", side_effect=_factory):
            result = dialog.show_sync_preview(
                parent, plan, position_window=position_window,
                apply_theme=apply_theme, button_factory=button_factory,
                palette=palette,
            )
        self.last_widgets = list(_widgets)
        self.last_window = parent.window
        self.last_parent = parent
        return result

    def _texts(self):
        return [str(widget.text) for widget in self.last_widgets]

    def test_cancel_button_returns_false(self):
        self.assertFalse(self._show("cancel"))

    def test_window_close_returns_false_like_cancel(self):
        self.assertFalse(self._show("close"))

    def test_cancel_and_window_close_release_the_grab_and_destroy_dialog(self):
        for action in ("cancel", "close"):
            with self.subTest(action=action):
                self.assertFalse(self._show(action))
                self.assertIsNone(self.last_parent.current_grab)
                self.assertTrue(self.last_window.destroyed)

    def test_dialog_can_be_opened_and_closed_repeatedly(self):
        for _ in range(3):
            self.assertFalse(self._show("cancel"))
            self.assertIsNone(self.last_parent.current_grab)
            self.assertTrue(self.last_window.destroyed)

    def test_final_position_is_set_while_hidden_before_first_visible_frame(self):
        self._show("cancel")
        self.assertTrue(self.last_window.withdrawn)
        self.assertTrue(self.last_window.visible)
        self.assertEqual(self.last_window.geometry_history, [("430x250+335+325", False)])

    def test_host_position_callback_runs_before_dialog_is_shown(self):
        observations = []

        def position(window):
            observations.append((window.withdrawn, window.visible))
            window.geometry("430x250+400+300")

        self._show("cancel", position_window=position)
        self.assertEqual(observations, [(True, False)])
        self.assertEqual(self.last_window.geometry_value, "430x250+400+300")
        self.assertFalse(self.last_window.geometry_history[-1][1])

    def test_edmc_theme_callback_receives_frame_widget_not_toplevel(self):
        themed = []

        def edmc_theme_update(widget):
            if isinstance(widget, FakeWindow):
                raise TypeError("Expected widget, got <class 'tkinter.Toplevel'>")
            themed.append(widget)

        self.assertFalse(self._show("cancel", apply_theme=edmc_theme_update))
        self.assertEqual(len(themed), 1)
        self.assertIsNot(themed[0], self.last_window)
        self.assertIsNone(self.last_parent.current_grab)

    def test_theme_api_type_error_is_logged_and_preview_remains_usable(self):
        def broken_theme_update(_widget):
            raise TypeError("Expected widget, got <class 'tkinter.Toplevel'>")

        with self.assertLogs(dialog.logger, level="ERROR") as captured:
            self.assertFalse(self._show("cancel", apply_theme=broken_theme_update))
        self.assertTrue(any("TypeError" in message for message in captured.output))
        self.assertIsNone(self.last_parent.current_grab)
        self.assertTrue(self.last_window.destroyed)

    def test_host_theme_palette_and_button_factory_are_applied(self):
        created = []

        def themed_button(*args, **kwargs):
            widget = _factory(*args, **kwargs)
            created.append(widget)
            return widget

        palette = {
            "background": "#101010", "foreground": "#f0f0f0",
            "muted": "#888888", "selected_bg": "#d0d0d0",
            "border": "#777777", "font_family": "Segoe UI",
        }
        self.assertTrue(self._show(
            "confirm",
            plan={"commander": "CMDR", "new": 1, "modified": 0,
                  "unchanged": 0, "credential_missing": 0},
            palette=palette,
            button_factory=themed_button,
        ))
        self.assertEqual(self.last_window.kwargs["background"], "#101010")
        self.assertEqual([w.text for w in created], ["Confirm Sync", "Cancel"])
        self.assertTrue(all("bg" not in w.kwargs and "fg" not in w.kwargs for w in created))
        labels = [w for w in self.last_widgets if w.text in {"Commander", "CMDR"}]
        self.assertTrue(all(w.kwargs["font"][0] == "Segoe UI" for w in labels))

    def test_confirmation_window_is_compact_and_centered_on_parent(self):
        self._show("cancel")
        self.assertEqual(self.last_window.title_value, "Confirm Synchronization")
        self.assertEqual(self.last_window.geometry_value, "430x250+335+325")

    def test_minimized_parent_falls_back_to_primary_screen_center(self):
        self._show("cancel", parent_state="iconic")
        self.assertEqual(self.last_window.geometry_value, "430x250+745+415")
        self.assertEqual(self.last_window.transient_args, ("",))

    def test_unmapped_or_invalid_parent_falls_back_to_primary_screen_center(self):
        parent = FakeParent("cancel")
        parent.winfo_ismapped = lambda: False
        self.assertEqual(
            dialog._centered_geometry(parent, 430, 250, 1920, 1080),
            "430x250+745+415",
        )
        parent.winfo_ismapped = lambda: True
        parent.winfo_rootx = lambda: -32000
        self.assertEqual(
            dialog._centered_geometry(parent, 430, 250, 1920, 1080),
            "430x250+745+415",
        )

    def test_dialog_position_is_clamped_inside_primary_screen(self):
        parent = FakeParent("cancel")
        parent.winfo_rootx = lambda: 1900
        parent.winfo_rooty = lambda: 1060
        self.assertEqual(
            dialog._centered_geometry(parent, 430, 250, 1920, 1080),
            "430x250+1474+814",
        )

    def test_empty_plan_shows_up_to_date_and_disables_confirm(self):
        self.assertFalse(self._show("confirm"))
        self.assertIn("All deposits are up to date", self._texts())
        confirm = next(w for w in self.last_widgets if w.text == "Confirm Sync")
        self.assertEqual(confirm.kwargs.get("state"), dialog.tk.DISABLED)
        self.assertEqual(confirm.kwargs.get("bg"), "#202020")

    def test_counts_ready_message_and_hides_technical_details(self):
        plan = {
            "source_type": "rs_api", "source_path": "private/source/rs_api.py",
            "commander": "CMDR Test", "records_found": 5, "records_valid": 5,
            "invalid": 1, "commander_mismatches": 1, "skipped": 2,
            "credential_missing": 0, "new": 2, "modified": 1,
            "unchanged": 2, "pending": [], "preview_pending": [],
        }
        self.assertTrue(self._show("confirm", plan))
        texts = self._texts()
        self.assertIn("CMDR Test", texts)
        self.assertIn("2", texts)
        self.assertIn("1", texts)
        self.assertIn("3 deposits ready to sync.", texts)
        self.assertIn("Skipped records: 2.", texts)
        self.assertNotIn("private/source/rs_api.py", texts)
        self.assertFalse(any("Report ID" in value or "Commodity" in value for value in texts))

    def test_missing_credentials_show_warning_and_disable_confirm(self):
        plan = {
            "commander": "CMDR", "invalid": 0, "commander_mismatches": 0,
            "credential_missing": 1, "new": 1, "modified": 0,
            "unchanged": 0,
        }
        self.assertFalse(self._show("confirm", plan))
        confirm = next(w for w in self.last_widgets if w.text == "Confirm Sync")
        self.assertEqual(confirm.kwargs.get("state"), dialog.tk.DISABLED)
        self.assertIn("1 deposit ready to sync.", self._texts())
        self.assertIn("API credentials missing for 1 deposit.", self._texts())

    def test_missing_credentials_without_ready_records_do_not_claim_up_to_date(self):
        plan = {
            "commander": "CMDR", "invalid": 0, "commander_mismatches": 0,
            "credential_missing": 1, "new": 0, "modified": 0,
            "unchanged": 0,
        }
        self.assertFalse(self._show("confirm", plan))
        texts = self._texts()
        self.assertIn("1 deposit needs API credentials before syncing.", texts)
        self.assertNotIn("All deposits are up to date", texts)
        self.assertNotIn("API credentials missing for 1 deposit.", texts)


if __name__ == "__main__":
    unittest.main()
