"""Real Tk message layout; no EDMC installation, credentials or HTTP."""
import tkinter as tk
from tkinter import font as tkfont
import unittest

from edmc_plugin.EDHF_Community_Navigator.message_label import (
    MessageLabel, sync_message,
)
from edmc_plugin.EDHF_Community_Navigator.dialog_layout import DialogBody
from edmc_plugin.EDHF_Community_Navigator.batch_protocol import outcome_summary, sync_failure_text


class MessageLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("360x800+0+0")
        self.original_scaling = self.root.tk.call("tk", "scaling")

    def tearDown(self):
        self.root.tk.call("tk", "scaling", self.original_scaling)
        self.root.destroy()

    def settle(self):
        self.root.update()

    def test_long_messages_wrap_without_expanding_host_and_shrink_after_resize(self):
        frame = tk.Frame(self.root)
        frame.pack(fill="x")
        label = MessageLabel(frame, text="Ready", font=("Segoe UI", 10))
        label.pack(fill="x")
        self.settle()
        short_height = label.winfo_reqheight()
        requested_width = self.root.winfo_reqwidth()
        for text in (
            "API key does not have the required permission. " * 6,
            "Status Report not confirmed. Use Status Report → Retry pending Status Report. " * 3,
            "Connection unavailable while scanning a system with a long name. " * 5,
            "X" * 220,
        ):
            label.config(text=text)
            self.settle()
            self.assertEqual(self.root.winfo_width(), 360)
            self.assertEqual(self.root.winfo_reqwidth(), requested_width)
            self.assertGreater(label.winfo_reqheight(), short_height)
            self.assertGreaterEqual(label.winfo_height(), label.winfo_reqheight())
            self.assertLessEqual(int(label.cget("wraplength")), label.winfo_width())
        narrow_height = label.winfo_reqheight()
        self.root.geometry("760x800+0+0")
        self.settle()
        self.assertLess(label.winfo_reqheight(), narrow_height)
        self.root.geometry("360x800+0+0")
        self.settle()
        self.assertEqual(label.winfo_reqheight(), narrow_height)
        stable = (label.winfo_width(), label.winfo_height(), label.cget("wraplength"))
        for _ in range(8):
            self.settle()
            self.assertEqual((label.winfo_width(), label.winfo_height(), label.cget("wraplength")), stable)
        label.config(text="Ready")
        self.settle()
        self.assertEqual(label.winfo_reqheight(), short_height)

    def test_empty_messages_release_space_and_restore_grid_or_pack(self):
        for manager in ("grid", "pack"):
            frame = tk.Frame(self.root)
            frame.pack(fill="x")
            frame.columnconfigure(0, weight=1)
            label = MessageLabel(frame, text="Ready")
            if manager == "grid":
                label.grid(row=0, column=0, sticky="ew")
            else:
                label.pack(fill="x")
            self.settle()
            label.configure(text="")
            self.settle()
            self.assertEqual(label.winfo_manager(), "")
            label.configure(text="Connection restored")
            self.settle()
            self.assertEqual(label.winfo_manager(), manager)
            self.assertGreater(label.winfo_height(), 1)
            frame.destroy()

    def test_theme_and_scaling_preserve_full_height_and_fit_dialog_before_mapping(self):
        for scaling in (1.0, 1.5, 2.0):
            self.root.tk.call("tk", "scaling", scaling)
            for bg, fg in (("#ffffff", "#101010"), ("#101410", "#f2f5f2")):
                window = tk.Toplevel(self.root)
                window.withdraw()
                layout = DialogBody(window, background=bg)
                outer = layout.content
                label = MessageLabel(outer, text="Status Report not confirmed. Use Status Report → Retry pending Status Report.",
                                     bg=bg, fg=fg, font=("Segoe UI", 10))
                label.pack(fill="x")
                button = tk.Button(layout.footer, text="Cancel")
                button.pack()
                layout.fit(self.root)
                window.deiconify()
                self.settle()
                self.assertEqual(label.cget("bg"), bg)
                self.assertEqual(label.cget("fg"), fg)
                self.assertGreaterEqual(label.winfo_height(), label.winfo_reqheight())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     window.winfo_rooty() + window.winfo_height())
                self.assertLessEqual(int(label.cget("wraplength")), label.winfo_width())
                window.destroy()

    def test_sync_summary_and_causes_are_separate_without_changing_meaning(self):
        summary = dict(synced=5, skipped=1, skipped_reports=[dict(error_code="STALE_UPDATE")],
                       pending_reports=[dict(recovery="credentials")] * 2 + [dict(recovery="retry")] * 5)
        text = sync_message(summary)
        self.assertEqual(text.splitlines()[0], outcome_summary(summary))
        self.assertNotIn(" | ", text)
        self.assertEqual(" ".join(text.splitlines()[1:]).lower(),
                         sync_failure_text(summary).replace("; ", ". ").lower())
        self.assertEqual(text.splitlines()[1:3], ["Outdated source version: 1 skipped.",
                         "Edit or re-mark in RhinoSpotter to supply a valid newer version."])
        self.assertIn("2 Pending — correct the API Key", text)
        self.assertIn("5 Pending — use Sync Bookmarks to retry", text)
        self.assertEqual(sync_message(dict(synced=12, skipped=0, pending_reports=[])),
                         "12 Synced · 0 Skipped · 0 Pending")


if __name__ == "__main__":
    unittest.main()
