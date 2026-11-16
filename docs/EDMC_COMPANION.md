# EDMC Companion — v1.0.5

The in-game plugin is **Hotspots Finder Deposits Companion**. Finder and EDMC use the same protected Community Deposits service; the desktop EXE and EDMC ZIP are separate downloads. This source tree prepares v1.0.5 stable; packages are not built or published by source preparation.

## Installation and packaging

Close EDMC and replace the existing `EDHF_Community_Navigator` folder's files with the future `Hotspots-Finder-EDMC-Plugin-v1.0.5.zip` contents. Keep one plugin folder with that name. Retain settings, Windows credentials, normal sync fingerprints and separate pending-event files; do not install smoke fixtures. Restart EDMC after replacing code. See the [plugin guide](../edmc_plugin/EDHF_Community_Navigator/README.md) for the full workflow.

Future packaging uses `build_companion_release.ps1` and the explicit 20-module allowlist in `release_manifest.json`. It includes README/LICENSE and excludes arbitrary extra files. Both future artifacts and SHA256.txt go in `release/v1.0.5/`; existing v1.0.4 artifacts remain untouched. No build or publication is part of source preparation.

## Commands and credentials

- Sync Bookmarks reads RhinoSpotter's public API and asks for confirmation. Scan System loads authenticated pages; Open Deposits reopens the cached system; Refresh Deposits refreshes stale data.
- System Deposits contains the compact community table and Status Report/Start Tracking below it. Amount, update columns and lower details panel are absent. Rigs and Density remain unchanged.
- Configure Community API Keys uses masked input and Windows Credential Manager. Read permits browsing/tracking; Write permits Sync and direct events. Permissions refresh on key changes without restarting, and stale asynchronous responses cannot grant old permissions.
- Start Tracking uses canonical target coordinates and a finite positive live radius or canonical fallback. Travel/approach guidance, heading and altitude-aware calculations are retained.
- The small title arrows move the whole section, preserving internal widget order. Their preference survives restart. Host geometry is checked before moving; limits/busy/unsupported layouts disable the arrows.

## Status Report

Select a canonical community deposit and choose Report Active or Report Depleted. Both options remain available for deliberate confirmations. Confirm the named deposit/state before sending; Cancel sends nothing. A valid Write key is required, but no RhinoSpotter bookmark is required. The Worker derives Commander from the key and records UTC database time.

A new confirmed click creates a new UUID/event, even for the same state. A technical retry reuses the original UUID. On an uncertain receipt the GUI shows **Status Report not confirmed. Use Status Report → Retry pending Status Report.** The operation survives restart; its menu entry disappears after a valid success receipt. No optimistic update or automatic retry queue is used. HTTP 429 waiting and credential errors remain explicit.

## Sync and shared state

Bookmark requests contain at most five reports. Synced is confirmed/previously confirmed unchanged; Skipped is a definite source/validation rejection; Pending is recoverable or uncertain. Bookmark recovery uses Sync Bookmarks; direct-event recovery uses the Status Report menu. Failed source versions are not silently counted as successful. Source timestamps and stable identity are preserved, including RhinoSpotter 6.6.0 nullable updated_at.

Individual snapshots never substitute for direct Active observations. The Worker preserves legacy baseline and monotonic verified depletion separately, resolving shared Active/Depleted with valid depletion times and explicit recorded_at events. Neither Sync time nor updated_at alone ranks shared observations. There is no automatic regeneration. Status uses calendar-day UTC age for precise dates and the original date for partial historical references.

## Update channel

Automatic checks use GitHub's latest stable release and recognize v1.0.5 as newer than v1.0.4 or the previous beta candidate. Prereleases and drafts are not offered. Neither checker downloads or installs updates automatically. Existing v1.0.4 packages must not be relabeled or reused as v1.0.5.
