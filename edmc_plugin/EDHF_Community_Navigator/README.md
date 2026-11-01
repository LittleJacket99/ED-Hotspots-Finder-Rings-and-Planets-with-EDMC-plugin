# Hotspots Finder EDMC Plugin

EDMarketConnector plugin for the **ED Hotspots Finder - Rings & Planets** ecosystem.

Inside EDMC the plugin is displayed as **Hotspots Finder Deposits Companion**.

Current version: **v1.0.4**.

The desktop application remains the main multi-system search and analysis client. The EDMC Plugin is the focused in-game client for synchronizing RhinoSpotter bookmarks, checking Community Deposits in the current system and navigating to a selected surface deposit.

## Current functionality

- **Sync Bookmarks** — reads RhinoSpotter 5.1+ through its documented `rs_api.py` interface, compares local stable-ID fingerprints and sends only new or modified bookmarks to Community Deposits.
- **Scan System** — queries Community Deposits for the system currently reported by EDMC.
- **Open Deposits** — reopens the cached result snapshot without another API request.
- **Refresh Deposits** — appears when a synchronization changed relevant data for the currently cached system.
- **No Deposits** — shown after a successful scan that returned no records.
- Results table with **Body, Location, Material, Rigs, Amount, Density, Depleted at, Latitude, Longitude, Reports and Updated**.
- **Start Tracking** — opens the compact surface-navigation HUD.
- Tracker display of compact body name, material, RhinoSpotter Location, relative direction and target distance.
- Altitude-aware distance while approaching a body.
- **Travel to <system>** and **Approach body <body>** guidance when the target is not yet suitable for surface navigation.
- **Open Finder** — launches the configured desktop Finder executable.
- Automatic update check on EDMC startup using the same GitHub release channel as the Finder.

Synchronization uses a shared local state file at `%APPDATA%\HotspotsFinder\rhinospotter_sync_state.json`. After the first successful sync, unchanged bookmarks are skipped locally; only new or fingerprint-changed bookmarks are sent to Community Deposits.

RhinoSpotter `revision()` is retained as metadata, but stable-ID fingerprints are the authoritative change detector so edits are not missed when the revision value itself does not change.

Server responses still distinguish new, matched, updated and unchanged reports, and an unchanged report does not falsely refresh the deposit's update time.

Community Deposits treats **Location**, **Material**, **Rigs**, **Amount**, **Density** and depletion state as meaningful mutable fields for synchronized RhinoSpotter bookmarks.

**Depleted at** displays **Active** for active deposits, or the depletion timestamp (`YYYY-MM-DD HH:MM:SS`) when RhinoSpotter has marked the bookmark depleted.

## Installation

Download the public package:

```text
Hotspots-Finder-EDMC-Plugin-v1.0.4.zip
```

Extract it into:

```text
%LOCALAPPDATA%\EDMarketConnector\plugins\
```

so the installed path becomes:

```text
%LOCALAPPDATA%\EDMarketConnector\plugins\EDHF_Community_Navigator\load.py
```

Then restart EDMarketConnector completely.

RhinoSpotter should be installed alongside it for bookmark synchronization:

```text
%LOCALAPPDATA%\EDMarketConnector\plugins\RhinoSpotter\rs_api.py
```

The plugin currently supports RhinoSpotter API `SCHEMA = 1`.

RhinoSpotter is required only for **Sync Bookmarks**. Community Deposits scanning and tracking work independently.

## Community Deposits API

The plugin uses the same service as the desktop application:

```text
GET  /v1/deposits?system=<system>
POST /v1/deposits/batch
```

No separate plugin database is introduced.

## Result caching

The plugin queries a system once and keeps that result snapshot locally while the commander remains in the same system.

The middle EDMC action changes between:

```text
Scan System
Open Deposits
Refresh Deposits
No Deposits
```

A system change clears the cache. A sync only marks the cached snapshot stale when the server reports a relevant data change.

## Navigator notes

The HUD is a frameless always-on-top Tk window intended for borderless/windowed Elite Dangerous desktop-overlay use.

It keeps a fixed palette for readability, remembers only its own screen position, and does not intentionally modify the EDMC main window geometry.

The tracker displays the compact body name, material and RhinoSpotter Location, plus a relative direction arrow and target distance. While approaching a body, altitude is combined with the surface separation so the displayed distance does not collapse to a few metres while the ship is still high above the target.
