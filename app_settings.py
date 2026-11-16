#!/usr/bin/env python3

"""Persistent settings for ED Hotspots Finder - Rings & Planets.

The v8 settings live under a dedicated key inside the existing
%APPDATA%\HotspotsFinder\config.json file so older configuration values are
preserved instead of being overwritten.
"""

import copy
import json
import os
from finder_distance import normalize_saved_distance
from pathlib import Path


APP_DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "HotspotsFinder"
CONFIG_PATH = APP_DATA_DIR / "config.json"
SETTINGS_KEY = "v8_settings"

DEFAULT_SETTINGS = {
    "startup": {
        "hotspots_enabled": True,
        "planets_enabled": True,
        "community_deposits_enabled": True,
        "max_distance_ly": 50.0,
        "remember_last_filters": False,
    },
    "rhinospotter": {
        # Empty means use the standard %LOCALAPPDATA%\RhinoSpotter data root.
        "data_path": "",
    },
    "community_api": {
        "commander": "",
    },
    "application": {
        "theme": "deep_black",
        "ui_scale": 1.15,
        "check_updates_on_startup": True,
    },
    "last_filters": {},
}


def _merge_defaults(defaults, saved):
    result = copy.deepcopy(defaults)
    if not isinstance(saved, dict):
        return result

    for key, value in saved.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_defaults(result[key], value)
        else:
            result[key] = value
    return result


def _read_root_config():
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_settings():
    root = _read_root_config()
    settings = _merge_defaults(DEFAULT_SETTINGS, root.get(SETTINGS_KEY, {}))
    # Older v1.0.4 configurations may contain this now-obsolete preference.
    # Ignore it so it can never affect the mandatory Sync Preview flow.
    settings.get("rhinospotter", {}).pop("ask_before_sync", None)
    settings["startup"]["max_distance_ly"] = normalize_saved_distance(settings["startup"].get("max_distance_ly"))
    return settings


def save_settings(settings):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = _read_root_config()
    normalized = _merge_defaults(DEFAULT_SETTINGS, settings)
    normalized.get("rhinospotter", {}).pop("ask_before_sync", None)
    normalized["startup"]["max_distance_ly"] = normalize_saved_distance(normalized["startup"].get("max_distance_ly"))
    root[SETTINGS_KEY] = normalized

    temp_path = CONFIG_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(root, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(CONFIG_PATH)


def default_rhinospotter_data_path():
    """Return RhinoSpotter's standard local-data root."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "RhinoSpotter"
    return Path.home() / "AppData" / "Local" / "RhinoSpotter"


def default_rhinospotter_cards_dir():
    """Backward-compatible alias retained for older callers.

    The GUI historically asked for RhinoSpotter's ``cards`` directory. Current
    RhinoSpotter releases store bookmarks in ``db\rhinospotter.db``, so the
    automatic location now points at the RhinoSpotter data root instead. The
    sync layer still accepts an actual legacy cards directory when one is
    explicitly configured.
    """

    return default_rhinospotter_data_path()


def resolve_rhinospotter_data_path(settings):
    """Resolve the configured RhinoSpotter source while preserving old configs."""

    rhino = (settings or {}).get("rhinospotter", {})

    custom = str(rhino.get("data_path", "") or "").strip()
    if custom:
        return Path(custom).expanduser()

    # v1.0.0 stored the same setting as ``cards_dir``. Keep accepting it so an
    # existing user's configuration continues to work without migration steps.
    legacy = str(rhino.get("cards_dir", "") or "").strip()
    if legacy:
        return Path(legacy).expanduser()

    return default_rhinospotter_data_path()


def resolve_rhinospotter_cards_dir(settings):
    """Backward-compatible alias retained for older callers."""

    return resolve_rhinospotter_data_path(settings)
