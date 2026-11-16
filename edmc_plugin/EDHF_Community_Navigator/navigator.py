from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Callable


ACCENT = "#5acd57"
BACKGROUND = "#101410"
TEXT = "#f2f5f2"
MUTED = "#a6b0a6"

HUD_WIDTH = 250
HUD_HEIGHT = 145


def _first(record: dict[str, Any], *keys: str):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_radius(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        radius = _float(value)
    except OverflowError:
        return None
    return radius if radius is not None and math.isfinite(radius) and radius > 0 else None


def _same_name(a: Any, b: Any) -> bool:
    if not a or not b:
        return False
    return str(a).strip().casefold() == str(b).strip().casefold()


def _compact_body_name(body: Any, system: Any = None) -> str:
    text = str(body or "Unknown").strip()
    system_text = str(system or "").strip()

    if system_text and text.casefold().startswith((system_text + " ").casefold()):
        suffix = text[len(system_text):].strip()
        if suffix:
            return "".join(suffix.split())

    return "".join(text.split())


def surface_distance_and_bearing(
    latitude: float,
    longitude: float,
    target_latitude: float,
    target_longitude: float,
    radius_m: float,
) -> tuple[float, float]:
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    lat2 = math.radians(target_latitude)
    lon2 = math.radians(target_longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    hav = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    central_angle = 2.0 * math.atan2(
        math.sqrt(hav),
        math.sqrt(max(0.0, 1.0 - hav)),
    )
    distance_m = radius_m * central_angle

    y = math.sin(dlon) * math.cos(lat2)
    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return distance_m, bearing


def signed_heading_delta(target_bearing: float, current_heading: float) -> float:
    return (target_bearing - current_heading + 540.0) % 360.0 - 180.0


def direction_arrow(delta: float) -> str:
    angle = (delta + 360.0) % 360.0
    if angle < 22.5 or angle >= 337.5:
        return "↑"
    if angle < 67.5:
        return "↗"
    if angle < 112.5:
        return "→"
    if angle < 157.5:
        return "↘"
    if angle < 202.5:
        return "↓"
    if angle < 247.5:
        return "↙"
    if angle < 292.5:
        return "←"
    return "↖"


def navigation_distance(
    surface_distance_m: float,
    altitude_m: float | None,
) -> float:
    """Combine horizontal surface separation with current altitude.

    Status.json altitude is the vertical component that the former
    surface-only distance ignored. Keeping the great-circle surface
    distance as the horizontal component also preserves useful ground/SRV
    navigation when altitude is zero or unavailable.
    """
    if altitude_m is None or altitude_m <= 0:
        return surface_distance_m

    return math.hypot(surface_distance_m, altitude_m)


def format_distance(distance_m: float) -> str:
    if distance_m < 1000.0:
        return f"{distance_m:.0f} m"
    return f"{distance_m / 1000.0:.2f} km"


class NavigatorOverlay:
    def __init__(
        self,
        master: tk.Misc,
        *,
        initial_x: int | None = None,
        initial_y: int = 120,
        on_position_changed: Callable[[int, int], None] | None = None,
    ):
        # Keep a reference to EDMC's top-level only so the overlay shares the
        # same Tcl interpreter. Its geometry is never used for the HUD.
        self.main_window = master.winfo_toplevel()
        self.window: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None

        self.target: dict[str, Any] | None = None
        self.target_system: str | None = None

        self._body_item: int | None = None
        self._material_item: int | None = None
        self._arrow_item: int | None = None
        self._distance_item: int | None = None

        self._drag_x = 0
        self._drag_y = 0
        if initial_x is None:
            screen_width = self.main_window.winfo_screenwidth()
            initial_x = max(0, (screen_width - HUD_WIDTH) // 2)

        self._window_x = int(initial_x)
        self._window_y = int(initial_y)
        self._on_position_changed = on_position_changed

    def start(self, record: dict[str, Any], current_system: str | None = None) -> None:
        self.target = dict(record)
        self.target_system = str(
            _first(record, "system", "system_name", "star_system")
            or current_system
            or ""
        ).strip() or None

        material = str(
            _first(record, "commodity", "material") or "Community deposit"
        )
        location = _first(record, "location_index", "location")
        material_line = material
        if location not in (None, ""):
            material_line = f"{material}  Location {location}"

        body = _first(record, "body", "body_name", "planet_name") or "Unknown"
        display_body = _compact_body_name(body, self.target_system)

        self._destroy_window(keep_target=True)
        self._create_window(material_line, display_body)

    def stop(self) -> None:
        self._destroy_window(keep_target=False)

    def destroy(self) -> None:
        self._destroy_window(keep_target=False)

    def update_status(
        self,
        status: dict[str, Any],
        *,
        current_system: str | None = None,
        current_body: str | None = None,
    ) -> None:
        if self.target is None or self.window is None or self.canvas is None:
            return

        if not self.window.winfo_exists():
            self.window = None
            self.canvas = None
            return

        target_body = _first(self.target, "body", "body_name", "planet_name")
        status_body = status.get("BodyName") or current_body

        if self.target_system and current_system and not _same_name(
            self.target_system, current_system
        ):
            self._set_navigation_text(
                "◎",
                f"Travel to\n{self.target_system}",
                compact=True,
            )
            return

        if target_body and status_body and not _same_name(target_body, status_body):
            self._set_navigation_text(
                "◎",
                f"Approach body {_compact_body_name(target_body, self.target_system)}",
                compact=True,
            )
            return

        latitude = _float(status.get("Latitude"))
        longitude = _float(status.get("Longitude"))
        heading = _float(status.get("Heading"))
        altitude = _float(status.get("Altitude"))
        target_lat = _float(_first(self.target, "latitude", "lat"))
        target_lon = _float(_first(self.target, "longitude", "lon", "lng"))
        radius = _positive_radius(status.get("PlanetRadius"))
        if radius is None:
            radius = _positive_radius(_first(self.target, "planet_radius", "body_radius"))

        if latitude is None or longitude is None:
            if target_body:
                self._set_navigation_text(
                    "◎",
                    f"Approach body {_compact_body_name(target_body, self.target_system)}",
                    compact=True,
                )
            else:
                self._set_navigation_text("•", "Waiting for position")
            return

        if target_lat is None or target_lon is None:
            self._set_navigation_text("!", "No target coordinates")
            return

        if radius is None or radius <= 0:
            self._set_navigation_text("•", "Waiting for planet radius")
            return

        surface_distance_m, bearing = surface_distance_and_bearing(
            latitude,
            longitude,
            target_lat,
            target_lon,
            radius,
        )
        distance_m = navigation_distance(
            surface_distance_m,
            altitude,
        )

        if heading is None:
            arrow = "↑"
        else:
            delta = signed_heading_delta(bearing, heading)
            arrow = direction_arrow(delta)

        self._set_navigation_text(arrow, format_distance(distance_m))

    def _set_navigation_text(
        self,
        arrow: str,
        distance: str,
        *,
        compact: bool = False,
    ) -> None:
        if self.canvas is None:
            return
        if self._arrow_item is not None:
            self.canvas.itemconfigure(self._arrow_item, text=arrow)
        if self._distance_item is not None:
            self.canvas.itemconfigure(
                self._distance_item,
                text=distance,
                width=HUD_WIDTH - 24,
                font=(
                    "Segoe UI",
                    9 if compact else 13,
                    "bold",
                ),
            )

    def _create_window(self, material: str, display_body: str) -> None:
        # Guard EDMC's own geometry. The overlay must never become the source
        # of the main application's saved window position.
        main_geometry = self.main_window.winfo_geometry()
        window = tk.Toplevel(self.main_window)
        self.window = window
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        try:
            window.attributes("-alpha", 0.94)
        except tk.TclError:
            pass

        try:
            window.wm_transient("")
        except tk.TclError:
            pass

        window.configure(background=BACKGROUND)
        window.resizable(False, False)
        window.geometry(
            f"{HUD_WIDTH}x{HUD_HEIGHT}+{self._window_x}+{self._window_y}"
        )

        canvas = tk.Canvas(
            window,
            width=HUD_WIDTH,
            height=HUD_HEIGHT,
            background=BACKGROUND,
            highlightthickness=1,
            highlightbackground=ACCENT,
            bd=0,
        )
        self.canvas = canvas
        canvas.pack(fill=tk.BOTH, expand=True)

        self._body_item = canvas.create_text(
            12,
            14,
            text=f"Body: {display_body}",
            fill=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self._material_item = canvas.create_text(
            12,
            38,
            text=material,
            fill=ACCENT,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self._arrow_item = canvas.create_text(
            HUD_WIDTH / 2,
            85,
            text="•",
            fill=ACCENT,
            font=("Segoe UI Symbol", 30, "bold"),
            anchor="center",
        )
        self._distance_item = canvas.create_text(
            HUD_WIDTH / 2,
            122,
            text="Waiting for position",
            fill=TEXT,
            font=("Segoe UI", 13, "bold"),
            anchor="center",
            width=HUD_WIDTH - 24,
            justify=tk.CENTER,
        )

        # Close control is drawn on the same canvas. Dragging works anywhere
        # else in the HUD, including over body/material/arrow/distance.
        canvas.create_text(
            HUD_WIDTH - 14,
            15,
            text="×",
            fill=MUTED,
            font=("Segoe UI", 10, "bold"),
            anchor="center",
            tags=("close",),
        )

        canvas.tag_bind("close", "<Button-1>", lambda _event: self.stop())
        canvas.bind("<ButtonPress-1>", self._drag_start)
        canvas.bind("<B1-Motion>", self._drag_move)
        canvas.bind("<ButtonRelease-1>", self._drag_end)

        window.lift()
        window.update_idletasks()

        # If creating the tool window caused Tk/Windows to alter EDMC's root
        # geometry, restore the exact previous geometry immediately.
        if self.main_window.winfo_geometry() != main_geometry:
            self.main_window.geometry(main_geometry)

    def _destroy_window(self, *, keep_target: bool) -> None:
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self._window_x = self.window.winfo_x()
                    self._window_y = self.window.winfo_y()
                    self.window.destroy()
            except tk.TclError:
                pass

        self.window = None
        self.canvas = None
        self._body_item = None
        self._material_item = None
        self._arrow_item = None
        self._distance_item = None

        if not keep_target:
            self.target = None
            self.target_system = None

    def _drag_start(self, event: tk.Event) -> None:
        if self.window is None:
            return

        # Do not start a drag when the close glyph itself was clicked.
        if self.canvas is not None:
            current = self.canvas.find_withtag("current")
            if current and "close" in self.canvas.gettags(current[0]):
                return

        self._drag_x = event.x_root - self.window.winfo_x()
        self._drag_y = event.y_root - self.window.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        if self.window is None:
            return

        main_geometry = self.main_window.winfo_geometry()

        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._window_x = x
        self._window_y = y
        self.window.geometry(f"+{x}+{y}")

        if self.main_window.winfo_geometry() != main_geometry:
            self.main_window.geometry(main_geometry)

    def _drag_end(self, _event: tk.Event) -> None:
        if self._on_position_changed is not None:
            self._on_position_changed(self._window_x, self._window_y)
