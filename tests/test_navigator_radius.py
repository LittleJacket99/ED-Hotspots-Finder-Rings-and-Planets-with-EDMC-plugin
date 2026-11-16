"""Exercise the real tracker update without windows, network or source bookmarks."""
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from edmc_plugin.EDHF_Community_Navigator import navigator


class NavigatorRadiusTests(unittest.TestCase):
    invalid = (None, "", "not numeric", 0, -1, float("nan"), float("inf"),
               float("-inf"), "NaN", "Infinity", "0", "-20", True, False)

    def tracker(self, radius=1_000_000):
        tracker = navigator.NavigatorOverlay.__new__(navigator.NavigatorOverlay)
        tracker.target = {"system": "Fixture", "body": "Body", "latitude": 12.5,
                          "longitude": -34.25, "planet_radius": radius}
        tracker.target_system = "Fixture"
        tracker.window = SimpleNamespace(winfo_exists=lambda: True)
        tracker.canvas = object()
        tracker._set_navigation_text = Mock()
        return tracker

    def status(self, **extra):
        return {"BodyName": "Body", "Latitude": 10, "Longitude": -30,
                "Heading": 270, "Altitude": 500, **extra}

    def update(self, tracker, status):
        tracker.update_status(status, current_system="Fixture", current_body="Body")

    def test_invalid_live_radii_fall_back_to_canonical_target_coordinates_and_radius(self):
        for value in self.invalid:
            with self.subTest(value=value):
                tracker = self.tracker()
                with patch.object(navigator, "surface_distance_and_bearing",
                                  wraps=navigator.surface_distance_and_bearing) as surface:
                    self.update(tracker, self.status(PlanetRadius=value))
                surface.assert_called_once_with(10.0, -30.0, 12.5, -34.25, 1_000_000.0)
                text = tracker._set_navigation_text.call_args.args[1]
                self.assertNotIn("Waiting", text)
                self.assertNotIn("nan", text)
                self.assertNotIn("inf", text)

    def test_missing_live_radius_uses_canonical_numeric_string_and_preserves_zero_coordinates(self):
        tracker = self.tracker("1000000")
        tracker.target.update(latitude=0, longitude=0)
        with patch.object(navigator, "surface_distance_and_bearing",
                          wraps=navigator.surface_distance_and_bearing) as surface:
            self.update(tracker, self.status())
        surface.assert_called_once_with(10.0, -30.0, 0.0, 0.0, 1_000_000.0)

    def test_valid_live_radius_has_priority_and_distance_altitude_heading_are_unchanged(self):
        for radius in (2_000_000, 2_000_000.5, "2000000"):
            with self.subTest(radius=radius):
                tracker = self.tracker()
                surface_distance, bearing = navigator.surface_distance_and_bearing(
                    10, -30, 12.5, -34.25, float(radius))
                expected_distance = math.hypot(surface_distance, 500)
                expected_arrow = navigator.direction_arrow(navigator.signed_heading_delta(bearing, 270))
                self.update(tracker, self.status(PlanetRadius=radius))
                tracker._set_navigation_text.assert_called_once_with(
                    expected_arrow, navigator.format_distance(expected_distance))

    def test_invalid_canonical_radius_with_invalid_live_radius_keeps_waiting_without_calculation(self):
        for radius in self.invalid:
            with self.subTest(radius=radius):
                tracker = self.tracker(radius)
                with patch.object(navigator, "surface_distance_and_bearing") as surface:
                    self.update(tracker, self.status(PlanetRadius=0))
                surface.assert_not_called()
                self.assertEqual(tracker._set_navigation_text.call_args.args[1], "Waiting for planet radius")

    def test_valid_live_radius_does_not_require_a_valid_canonical_radius(self):
        tracker = self.tracker(float("nan"))
        with patch.object(navigator, "surface_distance_and_bearing",
                          wraps=navigator.surface_distance_and_bearing) as surface:
            self.update(tracker, self.status(PlanetRadius=1_000_000))
        surface.assert_called_once_with(10.0, -30.0, 12.5, -34.25, 1_000_000.0)

    def test_existing_canonical_radius_alias_still_works(self):
        tracker = self.tracker(None)
        tracker.target["body_radius"] = 1_000_000
        with patch.object(navigator, "surface_distance_and_bearing",
                          wraps=navigator.surface_distance_and_bearing) as surface:
            self.update(tracker, self.status())
        self.assertEqual(surface.call_args.args[-1], 1_000_000.0)


if __name__ == "__main__":
    unittest.main()
