"""EDMC 6.1.2 wrapper layout reproduced with real Tk and isolated config."""
import tkinter as tk
import unittest
from unittest.mock import Mock

from edmc_plugin.EDHF_Community_Navigator.section_order import SectionOrder, POSITION_KEY


class Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.writes = []

    def get_int(self, key, default=0):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value
        self.writes.append((key, value))


class SectionOrderTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.box = tk.Frame(self.root)
        self.box.grid()
        tk.Label(self.box, text="Host controls", name="host_controls").grid(row=0, columnspan=2)
        self.panels = []
        for number in (1, 2, 3):
            separator = tk.Frame(self.box, name=f"plugin_hr_{number}")
            separator.grid(row=number * 2 - 1, columnspan=2, sticky="ew")
            panel = tk.Frame(self.box, name=f"plugin_{number}")
            panel.grid(row=number * 2, columnspan=2, sticky="nsew")
            self.panels.append(panel)
        self.frame = tk.Frame(self.panels[1])
        self.frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.controls = [tk.Label(self.frame, text=text) for text in
                         ("Title", "Sync Bookmarks", "Open Deposits", "Open Finder", "API Key", "Status")]
        for row, child in enumerate(self.controls):
            child.grid(row=row, column=0)
        self.settings = Settings()
        self.busy = False
        self.order = SectionOrder(self.frame, self.settings, is_busy=lambda: self.busy)
        self.up, self.down = tk.Label(self.frame), tk.Label(self.frame)
        self.order.attach(self.up, self.down)

    def tearDown(self):
        self.order.close()
        self.root.update_idletasks()
        self.root.destroy()

    def restore_once(self):
        # Simulate the scheduled callback without leaving its real Tk timer live.
        if self.order._timer is not None:
            self.frame.after_cancel(self.order._timer)
            self.order._timer = None
        self.order._restore(0)

    def names(self):
        return [item[1].winfo_name() for item in self.order._slots()]

    def test_up_down_keep_all_widgets_bindings_and_separators(self):
        before = [(child, child.grid_info(), child.cget("text")) for child in self.controls]
        callback = Mock()
        binding = self.controls[0].bind("<Button-1>", callback)
        self.order.refresh()
        self.assertEqual(self.up.cget("state"), "normal")
        self.assertTrue(self.order.move(-1))
        self.assertEqual(self.names(), ["plugin_2", "plugin_1", "plugin_3"])
        self.assertEqual(self.panels[1].grid_info()["row"], 2)
        self.assertEqual(self.box.children["plugin_hr_2"].grid_info()["row"], 1)
        self.assertTrue(self.order.move(1))
        self.assertEqual(self.names(), ["plugin_1", "plugin_2", "plugin_3"])
        for child, layout, text in before:
            self.assertTrue(child.winfo_exists())
            self.assertEqual(child.grid_info(), layout)
            self.assertEqual(child.cget("text"), text)
        self.assertIn(binding, self.controls[0].bind("<Button-1>"))
        self.assertEqual(len(set(self.box.winfo_children())), len(self.box.winfo_children()))
        self.assertTrue(all(key == POSITION_KEY for key, value in self.settings.writes))
        self.assertEqual(self.box.children["host_controls"].grid_info()["row"], 0)

    def test_boundaries_and_single_panel(self):
        self.order.move(-1)
        self.assertEqual(self.up.cget("state"), "disabled")
        self.assertFalse(self.order.move(-1))
        self.order.move(1)
        self.order.move(1)
        self.assertEqual(self.down.cget("state"), "disabled")
        self.assertFalse(self.order.move(1))
        for number in (1, 3):
            self.panels[number - 1].destroy()
            self.box.children[f"plugin_hr_{number}"].destroy()
        self.order.refresh()
        self.assertEqual(self.up.cget("state"), "disabled")
        self.assertEqual(self.down.cget("state"), "disabled")

    def test_busy_rejects_movement_even_if_button_was_enabled(self):
        self.busy = True
        self.order.refresh()
        self.assertEqual(self.up.cget("state"), "disabled")
        self.assertFalse(self.order.move(-1))
        self.assertEqual(self.settings.writes, [])
        self.busy = False
        self.order.refresh()
        self.assertTrue(self.order.move(-1))

    def test_restore_after_recreation_preserves_other_plugin_relative_order(self):
        self.order.move(1)
        persisted = dict(self.settings.values)
        self.order.close()
        for index, panel in enumerate(self.panels, 1):
            panel.grid_configure(row=index * 2)
            self.box.children[f"plugin_hr_{index}"].grid_configure(row=index * 2 - 1)
        self.settings = Settings(persisted)
        self.order = SectionOrder(self.frame, self.settings)
        self.order.attach(self.up, self.down)
        self.restore_once()  # Host has not finished loading yet.
        self.assertEqual(self.names(), ["plugin_1", "plugin_2", "plugin_3"])
        tk.Button(self.box, name="update_button").grid(row=7, columnspan=2)
        self.restore_once()
        self.assertEqual(self.names(), ["plugin_1", "plugin_3", "plugin_2"])
        self.assertEqual(self.settings.writes, [])

    def test_late_plugins_are_included_before_restore_and_saved_slot_is_clamped(self):
        self.settings.values[POSITION_KEY] = 99
        self.restore_once()
        panel = tk.Frame(self.box, name="plugin_4")
        panel.grid(row=8, columnspan=2)
        tk.Frame(self.box, name="plugin_hr_4").grid(row=7, columnspan=2)
        tk.Button(self.box, name="update_button").grid(row=9, columnspan=2)
        self.restore_once()
        self.assertEqual(self.names(), ["plugin_1", "plugin_3", "plugin_4", "plugin_2"])

    def test_unknown_or_overlapping_layout_fails_closed(self):
        self.box.children["plugin_hr_1"].destroy()
        self.order.refresh()
        self.assertFalse(self.order.move(-1))
        self.assertEqual(self.up.cget("state"), "disabled")
        self.assertEqual(self.settings.writes, [])

    def test_invalid_saved_position_does_not_reorder_or_write(self):
        tk.Button(self.box, name="update_button").grid(row=7, columnspan=2)
        self.settings.values[POSITION_KEY] = "invalid"
        self.restore_once()
        self.assertEqual(self.names(), ["plugin_1", "plugin_2", "plugin_3"])
        self.assertEqual(self.settings.writes, [])

    def test_busy_restore_waits_and_invalid_layout_is_not_persisted(self):
        self.settings.values[POSITION_KEY] = 0
        tk.Button(self.box, name="update_button").grid(row=7, columnspan=2)
        self.busy = True
        self.restore_once()
        self.assertEqual(self.names(), ["plugin_1", "plugin_2", "plugin_3"])
        self.busy = False
        self.restore_once()
        self.assertEqual(self.names()[0], "plugin_2")
        tk.Label(self.box, text="unexpected overlap").grid(row=2, columnspan=2)
        self.order.refresh()
        self.assertFalse(self.order.move(1))

    def test_real_plugin_header_is_small_themed_and_blocks_sync_and_status_moves(self):
        from types import SimpleNamespace
        from test_edmc_sync_preview_lifecycle import EdmcSyncPreviewLifecycleTests
        host = EdmcSyncPreviewLifecycleTests()
        module = host._with_plugin()
        self.addCleanup(host.doCleanups)
        for scaling in (96 / 72, 2.0, 8 / 3):
            self.root.tk.call("tk", "scaling", scaling)
            for bg, fg in (("#ffffff", "#101010"), ("#101410", "#f2f5f2")):
                box = tk.Frame(self.root)
                box.grid(row=1)
                panels = []
                for number in (1, 2, 3):
                    tk.Frame(box, name=f"plugin_hr_{number}").grid(row=number * 2 - 1, columnspan=2)
                    panel = tk.Frame(box, name=f"plugin_{number}")
                    panel.grid(row=number * 2, columnspan=2)
                    panels.append(panel)
                handlers = {}

                def theme_widget(widget):
                    for child in widget.winfo_children():
                        if isinstance(child, (tk.Label, tk.Frame)):
                            child.configure(background=bg)
                        if isinstance(child, tk.Label):
                            child.configure(foreground=fg)
                        theme_widget(child)

                module.theme = SimpleNamespace(update=theme_widget,
                                               button_bind=lambda w, command: handlers.setdefault(w, command))
                module.config = Settings()
                module.NavigatorOverlay = Mock()
                module._stopping = False
                module._ui_busy = False
                module._status_report_inflight = None
                frame = module.plugin_app(panels[1])
                frame.grid(columnspan=2)
                self.root.update_idletasks()
                order = module._section_order
                order.refresh()
                arrows = [w for w in handlers if w.cget("text") in ("▲", "▼")]
                self.assertEqual(len(arrows), 2)
                for arrow in arrows:
                    title = next(w for w in arrow.master.master.winfo_children() if isinstance(w, tk.Label))
                    self.assertEqual(title.cget("text"), "Alliance Community Deposits")
                    self.assertLessEqual(arrow.winfo_reqheight(), title.winfo_reqheight())
                    self.assertEqual(arrow.cget("background"), bg)
                    self.assertEqual(arrow.cget("foreground"), fg)
                    self.assertEqual(str(arrow.cget("width")), "1")
                widgets = set(frame.winfo_children())
                up = next(w for w in arrows if w.cget("text") == "▲")
                handlers[up]()
                self.assertEqual(panels[1].grid_info()["row"], 2)
                module._set_busy(True, "Sync in progress")
                self.assertFalse(order.move(1))
                self.assertEqual(order.down.cget("state"), "disabled")
                module._set_busy(False, "Ready")
                module._status_report_inflight = ("Synthetic", 1)
                order.refresh()
                self.assertFalse(order.move(1))
                module._status_report_inflight = None
                self.assertEqual(set(frame.winfo_children()), widgets)
                self.assertEqual(frame.master, panels[1])
                module.plugin_stop()
                # plugin_app's pre-existing update-check timer is unrelated to
                # ordering. This test destroys/recreates its frame in one Tk app.
                for timer in self.root.tk.call("after", "info"):
                    script = self.root.tk.call("after", "info", timer)[0]
                    if "_start_update_check" in str(script):
                        frame.after_cancel(timer)
                self.root.update_idletasks()
                box.destroy()


if __name__ == "__main__":
    unittest.main()
