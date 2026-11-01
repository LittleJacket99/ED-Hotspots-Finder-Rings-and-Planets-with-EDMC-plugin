import unittest
from pathlib import Path

from hotspots_finder_gui_v8_settings import settings_window_metrics


class SettingsLayoutMetricsTests(unittest.TestCase):
    def test_sections_and_footer_fit_at_supported_scales(self):
        for scale in (1.00, 1.15, 1.25):
            with self.subTest(scale=scale):
                metrics = settings_window_metrics(scale, screen_height=768)
                self.assertLessEqual(metrics["physical_height"], 728)
                content_bottom = 507 if metrics["compact_layout"] else 608
                self.assertLessEqual(content_bottom, metrics["actions_y"])
                self.assertLessEqual(
                    metrics["actions_y"] + 28,
                    metrics["logical_height"],
                )

    def test_compact_spacing_fits_on_a_short_screen_at_100_percent(self):
        metrics = settings_window_metrics(
            1.00,
            screen_height=577,
        )
        self.assertTrue(metrics["compact_layout"])
        self.assertLessEqual(507, metrics["actions_y"])
        self.assertLessEqual(metrics["actions_y"] + 28, metrics["logical_height"])

    def test_settings_implementation_has_no_scroll_widgets_or_canvas(self):
        source = (Path(__file__).resolve().parents[1] / "hotspots_finder_gui_v8_settings.py").read_text(encoding="utf-8")
        for obsolete in ("tk.Canvas(", "tk.Scrollbar(", "create_window(", "scrollregion=", ".xview", ".yview"):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, source)


if __name__ == "__main__":
    unittest.main()
