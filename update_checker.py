#!/usr/bin/env python3

"""GitHub release update checking for ED Hotspots Finder."""

import json
import re
import urllib.error
import urllib.request


LATEST_RELEASE_API = (
    "https://api.github.com/repos/"
    "LittleJacket99/ED-Hotspots-Finder-Rings-and-Planets-with-EDMC-plugin/releases/latest"
)
LATEST_RELEASE_PAGE = (
    "https://github.com/LittleJacket99/"
    "ED-Hotspots-Finder-Rings-and-Planets-with-EDMC-plugin/releases/latest"
)


def _version_tuple(value):
    """Order a beta below its stable release, retaining numeric version order."""

    text = str(value or "").strip()
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-beta\.([1-9]\d*))?", text)
    if not match:
        return None
    major, minor, patch, beta = match.groups()
    return (int(major), int(minor or 0), int(patch or 0),
            1 if beta is None else 0, int(beta or 0))


def check_for_update(current_version, timeout=4.0):
    """Query the latest public GitHub Release without blocking app startup.

    Drafts and prereleases are ignored by the GitHub releases/latest endpoint.
    Network/API failures are returned quietly so update checking can never stop
    the application from starting.
    """

    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ED-Hotspots-Finder-Rings-and-Planets/{current_version}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)

        latest_version = str(payload.get("tag_name") or "").strip()
        current_key = _version_tuple(current_version)
        latest_key = _version_tuple(latest_version)
        if (current_key is None or latest_key is None or latest_key[3] != 1
                or payload.get("prerelease") or payload.get("draft")):
            raise ValueError("GitHub returned an unsupported version tag")

        return {
            "ok": True,
            "update_available": latest_key > current_key,
            "current_version": str(current_version),
            "latest_version": latest_version,
            "release_url": str(payload.get("html_url") or LATEST_RELEASE_PAGE),
            "release_name": str(payload.get("name") or latest_version),
        }
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        return {
            "ok": False,
            "update_available": False,
            "current_version": str(current_version),
            "latest_version": "",
            "release_url": LATEST_RELEASE_PAGE,
            "error": str(exc),
        }
