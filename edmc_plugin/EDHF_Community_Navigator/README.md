# Hotspots Finder Deposits Companion — v1.0.5

EDMarketConnector plugin for ED Hotspots Finder - Rings & Planets. This source tree prepares **v1.0.5 stable**; no packages are built or published by this preparation. Existing v1.0.4 packages remain historical artifacts.

## Installation and update from v1.0.4

Use the future **Hotspots-Finder-EDMC-Plugin-v1.0.5.zip**, not the Finder EXE. Close EDMC, extract the package, and replace the files in the existing **EDHF_Community_Navigator** plugin folder under `%LOCALAPPDATA%\EDMarketConnector\plugins\`. Keep that folder name; do not install a second version-named plugin alongside it. Restart EDMC. Retain existing configuration, credentials, sync cache and pending files; do not copy an isolated smoke profile into the normal installation.

The desktop EXE is installed separately and can be selected for **Open Finder**. RhinoSpotter is a separate plugin by Fumlop and is required only for Sync Bookmarks, not for community browsing, tracking or direct Status Reports.

## Access and commands

Community Deposits are restricted to authorized API-key holders. **Read** permits scanning/browsing/tracking. **Write** permits bookmark synchronization and direct Status Reports; using all functions normally requires both permissions. Configure the Commander's key with **Configure Community API Keys**. Fields are masked; credentials are stored in Windows Credential Manager, not plugin preferences or release files. Changing keys rechecks permissions without restarting and discards stale results from the previous credential session.

- **Sync Bookmarks** reads the documented RhinoSpotter API, compares stable-ID fingerprints and sends only eligible changed/new reports after **Confirm Synchronization**. Cancel sends nothing.
- **Scan System**, **Open Deposits**, **Refresh Deposits** and **No Deposits** reflect the current system's authenticated result cache. Reads follow all cursor pages.
- **System Deposits** displays Body, Location, Material, Rigs, Density, Status, Latitude, Longitude and Reports. Amount remains stored but hidden. There is no bottom details panel or State reference/Last Update/Last Report column.
- **Start Tracking** navigates to the selected canonical deposit. Valid live Status.json radius takes precedence; invalid/missing live radius falls back to the canonical finite positive radius. Invalid radii are never used in distance calculations.
- **Status Report** offers **Report Active** and **Report Depleted**, even to confirm the same state again. Select a canonical deposit, then confirm the named deposit/state. No bookmark is required. Cancel sends nothing. Read-only keys cannot report.
- **▲ ▼** move the complete Companion section one place at a time. The plugin stores only its own position preference and restores it after EDMC restarts. Arrows are disabled at limits or while busy. Unknown host layouts disable ordering safely.
- **Open Finder** launches the configured desktop EXE.

## Sync results and retries

The summary is **N Synced · M Skipped · P Pending**.

- **Synced**: confirmed by the Worker, or locally unchanged since a previous confirmed sync. An invariant sync sends no new batch.
- **Skipped**: a definite validation or temporal rejection such as STALE_UPDATE or ACTIVE_TRANSITION_UNVERIFIABLE. Edit or re-mark the source to supply an eligible real version; repeating identical source data is not a recovery.
- **Pending**: temporary errors, authentication problems or an uncertain receipt. For recoverable bookmarks use **Sync Bookmarks** again; fix API Key/Write permissions first when indicated.

Requests contain at most **five reports**, with pacing. Successful items are retained when other items/batches fail. HTTP 429 stops later sends for that Commander; wait as directed before manually retrying. There is no automatic resend queue. The client never invents source timestamps.

Direct reports have a separate pending store. A lost receipt keeps the original Commander, deposit, state and operation UUID across restarts. Use **Status Report → Retry pending Status Report**. A retry retains the original event/time and does not create another event. A new confirmed deliberate report uses a new UUID. Success is shown only after a valid Worker receipt; responses from an old Commander session are ignored.

## Shared state and RhinoSpotter 6.6.0

RhinoSpotter `marked_at` is the original bookmark time. `updated_at` is Edit/Re-mark time and can be None. Tons mined, Mark depleted and automatic 40-day removal of Depleted do not necessarily advance it. API timestamps with a space and six decimal places are preserved.

Individual reports remain separate. The Worker can accept a strictly newer valid depletion time without a newer content version only if all other content/technical values are unchanged. An unversioned Active transition is not forced; it is Skipped with an explanation. An Active bookmark, Re-mark or Edit is not automatically proof of a new shared Active observation.

Shared state comes from retained valid depletion evidence or explicit direct reports, preserving the legacy baseline. Later comparable evidence wins; conflicting equal times resolve conservatively to Depleted. No automatic regeneration exists in this database. Rigs/Density stay unchanged in v1.0.5.

**Status** shows Active or Depleted with UTC calendar-day age when a complete valid time exists. A date-only legacy reference is displayed as its original date, without inventing a time. Provenance and original timestamps remain in the data; the compact GUI does not add a details panel.

## Updates and packaging

Automatic checks use GitHub's latest stable release and recognize v1.0.5 as newer than v1.0.4 or the previous beta candidate. Prereleases and drafts are not offered. Neither checker downloads or installs updates automatically. Existing v1.0.4 packages must not be relabeled or reused as v1.0.5.

`build_companion_release.ps1` is prepared to package the 20 modules declared in `release_manifest.json`, this README and LICENSE only. It keeps the installation folder name and writes solely to `release/v1.0.5/`. Smoke guards, synthetic plugins, caches, personal configuration, keys, tests and admin tools are excluded.
