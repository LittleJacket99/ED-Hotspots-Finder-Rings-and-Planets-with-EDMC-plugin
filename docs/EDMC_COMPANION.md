# Hotspots Finder EDMC Plugin

**Hotspots Finder EDMC Plugin** is the public GitHub package name for the EDMarketConnector extension of the **ED Hotspots Finder - Rings & Planets** ecosystem.

Inside EDMC it is displayed as **Hotspots Finder Deposits Companion**.

The desktop Finder remains the main multi-system search, planning and analysis client. The EDMC Plugin is the lightweight in-game client for synchronizing RhinoSpotter bookmarks, checking Community Deposits in the current system and navigating to a selected surface deposit.

Both clients use the same **Community Deposits** service and the same public release version.

## Product roles

### ED Hotspots Finder - Rings & Planets

- multi-system Hotspots, Planets and Community Deposits searches;
- system discovery and filtering;
- Powerplay-oriented research;
- result sorting, column filtering and CSV/XLSX export;
- RhinoSpotter contribution synchronization;
- Community Deposits results including Location, Rigs, Amount, Density, depletion status and update information.

### Hotspots Finder EDMC Plugin

- compact EDMC interface;
- RhinoSpotter bookmark synchronization;
- current-system Community Deposits lookup;
- cached reopening of already scanned results;
- refresh only when relevant synchronized data changed;
- selected-deposit navigation through an always-on-top HUD;
- direct launch of the desktop Finder;
- automatic background update check when EDMC starts.

## Runtime flow

```text
RhinoSpotter rs_api
        |
        | Sync Bookmarks
        v
Community Deposits API
        ^
        |
        | Scan System / Refresh Deposits
        |
EDMC current system
        |
        v
Results window
        |
        | Start Tracking
        v
Status.json / dashboard_entry
        |
        v
Navigator HUD
```

## Main EDMC controls

The plugin exposes three compact actions inside EDMC:

- **Sync Bookmarks** — reads RhinoSpotter 5.1+ through its documented `rs_api.py` interface, compares stable bookmark fingerprints locally and sends only new or modified bookmarks.
- **Scan System** — queries Community Deposits for the system currently reported by EDMC.
- **Open Finder** — launches the configured ED Hotspots Finder executable.

After a successful scan, the middle action becomes:

- **Open Deposits** when the current result snapshot is still valid;
- **Refresh Deposits** when a synchronization changed Community Deposits data relevant to the current system;
- **No Deposits** when the scanned system returned no records.

Closing the results window does not force another API query while the commander remains in the same system. Changing system clears the old cache and closes stale results.

## Screenshots

### EDMC controls

![Hotspots Finder EDMC Plugin panel](images/edmc-plugin-panel.png)

### Community Deposits results

![Hotspots Finder EDMC Plugin Community Deposits results](images/edmc-plugin-results.png)

### Navigation HUD

![Hotspots Finder EDMC Plugin navigation tracker](images/edmc-plugin-tracker.png)

## Synchronization semantics

A stable `report_id` is generated for each RhinoSpotter bookmark so repeated synchronization does not intentionally create duplicate report identities.

Before contacting Community Deposits, the plugin compares each bookmark against a shared local fingerprint cache:

```text
%APPDATA%\HotspotsFinder\rhinospotter_sync_state.json
```

After the initial synchronization, unchanged bookmarks are skipped locally. If one bookmark is edited, only that changed bookmark is uploaded. The desktop Finder uses the same state file.

RhinoSpotter `revision()` is retained as metadata, but it is not used as the sole skip condition because an unchanged revision value is not sufficient to prove that every bookmark row is unchanged. Stable-ID fingerprints are the authoritative comparison.

The Community Deposits backend distinguishes:

- `inserted` — a new deposit/report;
- `matched_existing_deposit` — a new report matched to an already known deposit;
- `updated_report` — an existing report whose meaningful mutable state changed;
- `unchanged` — the same report was synchronized again without a meaningful change.

A bookmark that is unchanged locally normally never reaches the backend at all. If a record is sent and the backend still determines that it is unchanged, repeated synchronization does not refresh the visible **Updated** timestamp just because the user pressed **Sync Bookmarks**.

Current deposit update policy for synchronized RhinoSpotter bookmarks:

- **Location** — mutable;
- **Material** — mutable;
- **Rigs** — mutable;
- **Amount** — mutable;
- **Density** — mutable;
- **depletion state** — mutable;
- missing technical metadata such as body ID or planet radius may be completed without counting as a meaningful deposit update.

A change to one of those mutable bookmark values is treated as an update. Synchronizing the same values again returns `unchanged`.

## RhinoSpotter integration

Current RhinoSpotter releases are consumed through the documented external API:

```text
%LOCALAPPDATA%\EDMarketConnector\plugins\RhinoSpotter\rs_api.py
```

The plugin supports RhinoSpotter API `SCHEMA = 1`.

The EDMC Plugin intentionally uses `rs_api.py` only.

The desktop Finder also prefers `rs_api.py`, but retains read-only SQLite and legacy JSON readers as compatibility fallbacks for older RhinoSpotter installations.

If RhinoSpotter is missing, **Sync Bookmarks** reports that RhinoSpotter 5.1+ must be installed as an EDMC plugin.

## Results window

The Community Deposits results window:

- inherits the current EDMC colour theme;
- shows **Body, Location, Material, Rigs, Amount, Density, Depleted at, Latitude, Longitude, Reports and Updated**;
- displays up to 10 rows before adding a vertical scrollbar;
- provides **Start Tracking** for the selected deposit.

The **Location** value comes from the RhinoSpotter bookmark location index stored by Community Deposits.

**Depleted at** shows **Active** while the shared deposit is active. When a commander marks the RhinoSpotter bookmark depleted and synchronizes it, the column shows the depletion timestamp as `YYYY-MM-DD HH:MM:SS`. If the bookmark is later set active again and synchronized, the value returns to **Active**.

## Navigator HUD

The tracker is intentionally compact and uses a fixed high-contrast palette independent of the EDMC theme.

It is:

- frameless;
- always on top;
- draggable;
- independently position-persistent;
- reopened cleanly when tracking starts again.

The HUD shows the compact body name together with material and RhinoSpotter **Location**.

When the selected deposit is in another system, the tracker shows **Travel to <system>**. When the ship is still too far from the target body for useful surface coordinates, it shows **Approach body <body>**.

Once surface navigation data is available, the plugin combines the target coordinates with live `Status.json` data from `dashboard_entry()` to calculate great-circle surface separation, bearing and a heading-relative direction arrow. When altitude is available, it is combined with the surface separation so the displayed target distance remains useful during aerial approach.

## Installation

Download:

```text
Hotspots-Finder-EDMC-Plugin-v1.0.4.zip
```

Extract it so this path exists:

```text
%LOCALAPPDATA%\EDMarketConnector\plugins\EDHF_Community_Navigator\load.py
```

Then restart EDMarketConnector completely.

RhinoSpotter 5.1+ is required only for **Sync Bookmarks**. Community Deposits scanning and tracking can still be used independently.

## Release packaging

Finder and EDMC Plugin are published together in one GitHub Release and share the same public release version. The first public release containing the plugin was **v1.0.2**; the current prepared release is **v1.0.4**.

The plugin source lives in:

```text
edmc_plugin/EDHF_Community_Navigator/
```

From the repository root, the release package can be generated with:

```powershell
.\build_companion_release.ps1
```

The script reads the version from `load.py` and creates:

```text
release\v1.0.4\Hotspots-Finder-EDMC-Plugin-v1.0.4.zip
release\v1.0.4\SHA256.txt
```

Finder and plugin assets are built into the same `release\v1.0.4` folder and share one `SHA256.txt`.
