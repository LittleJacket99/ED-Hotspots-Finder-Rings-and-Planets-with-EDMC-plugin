"""Actual EDMC dialog rendering, including small screens; never sends data."""
import tkinter as tk
from unittest.mock import patch
import unittest

from edmc_plugin.EDHF_Community_Navigator.dialog_layout import DialogBody
from edmc_plugin.EDHF_Community_Navigator.message_label import MessageLabel
from edmc_plugin.EDHF_Community_Navigator.edmc_sync_dialog import skipped_messages
from edmc_plugin.EDHF_Community_Navigator.sync_preview_dialog import show_sync_preview


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class DialogOverflowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("650x450+0+0")
        self.scaling = self.root.tk.call("tk", "scaling")

    def tearDown(self):
        self.root.tk.call("tk", "scaling", self.scaling)
        self.root.destroy()

    def test_one_stale_reason_once_and_multiple_causes_are_distinct(self):
        self.assertEqual(skipped_messages(dict(skipped=1, skipped_reports=[dict(error_code="STALE_UPDATE")])),
                         ["1 Skipped — edit or re-mark in RhinoSpotter to retry."])
        lines = skipped_messages(dict(skipped=4, invalid=1, commander_mismatches=1,
                                      skipped_reports=[dict(error_code="STALE_UPDATE"),
                                                       dict(error_code="ACTIVE_TRANSITION_UNVERIFIABLE")]))
        self.assertEqual(len(lines), 4)
        self.assertEqual(sum("re-mark" in line for line in lines), 1)
        self.assertEqual(sum("Active transition" in line for line in lines), 1)

    def test_actual_sync_dialog_with_host_positioning_keeps_buttons_and_single_skip(self):
        from test_edmc_sync_preview_lifecycle import EdmcSyncPreviewLifecycleTests
        host = EdmcSyncPreviewLifecycleTests()
        module = host._with_plugin()
        self.addCleanup(host.doCleanups)
        failures = []

        def inspect():
            try:
                window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
                self.root.update_idletasks()
                texts = [str(w.cget("text")) for w in descendants(window) if isinstance(w, tk.Label)]
                self.assertEqual(sum("Skipped" in s for s in texts), 1)
                for w in descendants(window):
                    if w.winfo_class() == "TButton":
                        self.assertLessEqual(w.winfo_rooty() + w.winfo_height(),
                                             window.winfo_rooty() + window.winfo_height())
                        self.assertGreaterEqual(w.winfo_rooty(), window.winfo_rooty())
                self.assertGreater(window.winfo_width(), 300)
            except Exception as error:
                failures.append(error)
            finally:
                window.destroy()

        self.root.after(100, inspect)
        result = show_sync_preview(self.root, dict(commander="Synthetic", new=0, modified=0, unchanged=11,
                                   skipped=1, skipped_reports=[dict(error_code="STALE_UPDATE")]),
                                   message_factory=MessageLabel,
                                   position_window=lambda w: module._center_credentials_window(w, self.root))
        self.assertFalse(result)
        if failures:
            raise failures[0]

    def test_long_content_scrolls_but_footer_remains_visible_at_multiple_scalings(self):
        for scaling in (1.0, 1.5, 2.0):
            self.root.tk.call("tk", "scaling", scaling)
            window = tk.Toplevel(self.root)
            window.withdraw()
            layout = DialogBody(window, background="#202020")
            MessageLabel(layout.content, text="Synthetic long warning. " * 250,
                         font=("Segoe UI", 10)).pack(fill="x")
            cancel = tk.Button(layout.footer, text="Cancel")
            cancel.pack(side="right")
            with patch.object(tk.Toplevel, "winfo_screenheight", return_value=360):
                layout.fit(self.root)
            window.deiconify()
            self.root.update()
            self.assertTrue(layout.bar.winfo_manager())
            self.assertLessEqual(cancel.winfo_rooty() + cancel.winfo_height(),
                                 window.winfo_rooty() + window.winfo_height())
            self.assertGreater(layout.content.winfo_reqheight(), layout.canvas.winfo_height())
            before = layout.canvas.yview()
            layout.canvas.yview_moveto(1)
            self.root.update()
            self.assertGreater(layout.canvas.yview()[0], before[0])
            self.assertAlmostEqual(layout.canvas.yview()[1], 1, places=2)
            window.destroy()

    def test_actual_api_key_dialog_has_reachable_save_for_long_commander(self):
        from test_edmc_sync_preview_lifecycle import EdmcSyncPreviewLifecycleTests
        host = EdmcSyncPreviewLifecycleTests()
        module = host._with_plugin()
        self.addCleanup(host.doCleanups)
        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True)
        module._frame = frame
        module._current_commander = "Synthetic Commander " * 180
        module._credentials_window = None
        with patch.object(tk.Toplevel, "winfo_screenheight", return_value=400):
            module._open_credentials_dialog()
        self.root.update()
        window = module._credentials_window
        save = next(w for w in descendants(window) if isinstance(w, tk.Button)
                    and w.cget("text") == "Save API Key")
        self.assertLessEqual(save.winfo_rooty() + save.winfo_height(),
                             window.winfo_rooty() + window.winfo_height())
        entries = [w for w in descendants(window) if isinstance(w, tk.Entry)]
        self.assertEqual(entries[0].cget("show"), "*")
        self.assertTrue(any(isinstance(w, tk.Canvas) and w.yview()[1] < 1 for w in descendants(window)))
        module.store_api_key.assert_not_called()
        window.destroy()

    def test_narrow_host_and_small_screen_keep_compact_dialog_buttons_visible(self):
        self.root.geometry("490x500+0+0")
        for percent in (100, 150, 200):
            self.root.tk.call("tk", "scaling", (96 / 72) * percent / 100)
            scale = self.root.winfo_fpixels("1i") / 96
            self.root.update()
            errors = []

            def inspect():
                window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
                try:
                    self.assertLessEqual(window.winfo_width(), 490)
                    for button in descendants(window):
                        if button.winfo_class() == "TButton":
                            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                                 window.winfo_rootx() + window.winfo_width())
                            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                                 window.winfo_rooty() + window.winfo_height())
                except Exception as error:
                    errors.append(error)
                finally:
                    window.destroy()

            self.root.after(80, inspect)
            with patch.object(tk.Toplevel, "winfo_screenwidth", return_value=round(340 * scale)), \
                    patch.object(tk.Toplevel, "winfo_screenheight", return_value=round(360 * scale)):
                show_sync_preview(self.root, dict(commander="Synthetic Commander " * 120,
                                                 new=1, modified=0, unchanged=11),
                                  message_factory=MessageLabel)
            if errors:
                raise errors[0]

    def test_sync_initial_width_is_compact_at_100_150_200_percent(self):
        from test_edmc_sync_preview_lifecycle import EdmcSyncPreviewLifecycleTests
        host = EdmcSyncPreviewLifecycleTests()
        module = host._with_plugin()
        self.addCleanup(host.doCleanups)
        cases = [dict(new=1, modified=0, unchanged=11, skipped=0),
                 dict(new=0, modified=0, unchanged=11, skipped=1,
                      skipped_reports=[dict(error_code="STALE_UPDATE")]),
                 dict(new=2, modified=1, unchanged=6, skipped=3, credential_missing=2,
                      skipped_reports=[dict(error_code=code) for code in
                                       ("STALE_UPDATE", "ACTIVE_TRANSITION_UNVERIFIABLE", "INVALID_REPORT")]),
                 dict(new=0, modified=0, unchanged=11, skipped=1,
                      commander="Synthetic Commander " * 150,
                      skipped_reports=[dict(error_code="STALE_UPDATE")])]
        for percent in (100, 150, 200):
            self.root.tk.call("tk", "scaling", (96 / 72) * percent / 100)
            dpi_scale = self.root.winfo_fpixels("1i") / 96
            self.root.geometry(f"{round(490 * dpi_scale)}x450+0+0")
            self.root.update()
            for index, case in enumerate(cases):
                errors = []

                def inspect():
                    window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
                    try:
                        self.root.update_idletasks()
                        logical_width = window.winfo_width() / dpi_scale
                        self.assertGreaterEqual(logical_width, 370, (percent, index, logical_width))
                        self.assertLessEqual(logical_width, 400, (percent, index, logical_width))
                        self.assertLessEqual(window.winfo_width(), self.root.winfo_width())
                        labels = [w for w in descendants(window) if isinstance(w, tk.Label)]
                        captions = [w for w in labels if w.cget("text") in ("New", "Modified", "Unchanged")]
                        self.assertEqual(len(captions), 3)
                        for label in captions:
                            self.assertGreaterEqual(label.winfo_width(), label.winfo_reqwidth())
                            self.assertLess(label.master.winfo_width(), window.winfo_width() / 2)
                            card = label.master
                            labels = card.winfo_children()
                            text_height = sum(item.winfo_reqheight() for item in labels)
                            old_height = text_height + 12 + 2 + 2  # padding, gap, border
                            self.assertLessEqual(card.winfo_height(), old_height - 10)
                            for item in labels:
                                self.assertGreaterEqual(item.winfo_height(), item.winfo_reqheight())
                        for widget in descendants(window):
                            if widget.winfo_class() == "TButton":
                                self.assertGreaterEqual(widget.winfo_rootx(), window.winfo_rootx())
                                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                                     window.winfo_rootx() + window.winfo_width())
                                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                                     window.winfo_rooty() + window.winfo_height())
                    except Exception as error:
                        errors.append(error)
                    finally:
                        window.destroy()

                self.root.after(80, inspect)
                plan = dict(commander="Synthetic", **case) if "commander" not in case else case
                show_sync_preview(self.root, plan, message_factory=MessageLabel,
                                  palette=dict(background="#ffffff" if index % 2 else "#202020",
                                               foreground="#101010" if index % 2 else "#eeeeee"),
                                  position_window=lambda w: module._center_credentials_window(w, self.root))
                if errors:
                    raise errors[0]


if __name__ == "__main__":
    unittest.main()
