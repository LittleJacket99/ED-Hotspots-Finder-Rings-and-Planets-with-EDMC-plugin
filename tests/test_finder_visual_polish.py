"""Finder visual changes: real Tk widgets, temporary settings, no HTTP."""
import ast
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image

import test_finder_final_settings as fixture
import ui_scale_runtime


class VisualPolishTests(unittest.TestCase):
    def setUp(self):
        self.gui = fixture.FinderGuiSettingsTests()
        self.gui.setUp()

    def tearDown(self):
        self.gui.tearDown()

    def test_logo_and_credit_layout_in_both_themes_and_scales(self):
        for theme in ("deep_black", "green_warm"):
            for scale in (1.0, 1.10, 1.15, 1.25):
                with self.subTest(theme=theme, scale=scale):
                    app = self.gui.create_app(theme=theme, scale=scale)
                    widgets = list(fixture.descendants(app))
                    photo = app._mahon_header_photo
                    self.assertIsNotNone(photo)
                    self.assertEqual(photo.height(), ui_scale_runtime.px(26))
                    self.assertEqual(photo.width(), photo.height())
                    logo = next(w for w in widgets if isinstance(w, tk.Label)
                                and str(w.cget("image")) == str(photo))
                    row = logo.master
                    block = row.master
                    labels = row.winfo_children()
                    self.assertEqual([w.cget("text") for w in labels[:-1]],
                                     ["Rings & Planets", "•", fixture.final_gui.PUBLIC_APP_VERSION, "•"])
                    # Check the image's full size, not just a compressed widget
                    # fitting inside its parent (which hid the original clipping).
                    self.assertEqual(logo.winfo_height(), photo.height())
                    self.assertEqual(logo.winfo_width(), photo.width())
                    logo_center = logo.winfo_y() + logo.winfo_height() / 2
                    for label in labels:
                        self.assertEqual(label.winfo_manager(), "pack")
                        self.assertLessEqual(abs(label.winfo_y() + label.winfo_height() / 2 - logo_center), 1)
                    self.assertGreaterEqual(logo.winfo_y(), 0)
                    self.assertLessEqual(logo.winfo_y() + photo.height(), row.winfo_height())
                    self.assertLessEqual(row.winfo_y() + row.winfo_height(), block.winfo_height())
                    header = block.master
                    self.assertLessEqual(block.winfo_y() + block.winfo_height(), header.winfo_height())
                    self.assertEqual(header.winfo_height(), ui_scale_runtime.px(76))
                    title = block.winfo_children()[0]
                    self.assertEqual(title.cget("text"), "ED Hotspots Finder")
                    credit = next(w for w in widgets if isinstance(w, tk.Label)
                                  and w.cget("text") == "Developed by CMDR LittleJacket")
                    link = next(w for w in widgets if isinstance(w, tk.Label)
                                and w.cget("text") == "GitHub Repository")
                    for widget, x in ((credit, 12), (link, 248)):
                        self.assertEqual(widget.winfo_x(), ui_scale_runtime.px(x))
                        self.assertEqual(widget.winfo_y(), ui_scale_runtime.px(100))
                        self.assertLessEqual(widget.winfo_y() + widget.winfo_height(),
                                             widget.master.winfo_height())
                    separator = next(w for w in credit.master.winfo_children()
                                     if isinstance(w, tk.Frame) and w.winfo_height() == ui_scale_runtime.px(1)
                                     and w.winfo_width() == ui_scale_runtime.px(540))
                    self.assertEqual(separator.winfo_y(), ui_scale_runtime.px(96))
                    self.assertLess(separator.winfo_y() + separator.winfo_height(), credit.winfo_y())
                    self.gui.destroy_app(app)

    def test_tooltip_exact_text_and_existing_style(self):
        app = self.gui.create_app()
        app._show_rhino_upload_help()
        label = app._rhino_help_popup.winfo_children()[0]
        self.assertEqual(label.cget("text"),
                         "Reads deposit reports saved locally by RhinoSpotter and syncs them with the "
                         "Community Deposits database. Matching reports are updated instead of being duplicated.\n\n"
                         "Community Deposits are accessible only to authorized users through a valid API key, "
                         "configurable in Settings.")
        self.assertEqual(int(label.cget("wraplength")), 310)
        self.assertEqual(label.cget("justify"), "left")

    def test_bundled_resource_resolution_and_safe_missing_resource(self):
        app = self.gui.create_app()
        directory = Path(self.gui.temp.name)
        (directory / "Mahon_logo.png").write_bytes((fixture.ROOT / "Mahon_logo.png").read_bytes())
        with patch.object(sys, "_MEIPASS", str(directory), create=True):
            self.assertEqual(app._load_mahon_header_image().height(), 26)
        with patch.object(sys, "_MEIPASS", str(directory / "missing"), create=True):
            self.assertIsNone(app._load_mahon_header_image())

    def test_png_transparency_and_pyinstaller_resource(self):
        with Image.open(fixture.ROOT / "Mahon_logo.png") as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
            for corner in ((0, 0), (239, 0), (0, 239), (239, 239)):
                self.assertEqual(image.getpixel(corner)[3], 0)
        tree = ast.parse((fixture.ROOT / "HotspotsFinder-v8.spec").read_text(encoding="utf-8"))
        datas = next(keyword.value for node in ast.walk(tree) if isinstance(node, ast.Call)
                     for keyword in node.keywords if keyword.arg == "datas")
        self.assertIn(("Mahon_logo.png", "."), ast.literal_eval(datas))
