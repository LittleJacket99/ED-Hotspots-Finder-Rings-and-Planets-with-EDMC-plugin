# ED Hotspots Finder + EDMC — v1.0.5

Stable release with improved Alliance Community Deposits integration, RhinoSpotter synchronization and desktop/plugin usability.

## Alliance Community Deposits

- Authenticated access with Read permissions for browsing/tracking and Write permissions for contributions.
- RhinoSpotter 6.6.0 support, preserving original bookmark timestamps and stable report identity.
- Incremental synchronization in batches of up to five, complete pagination, and clear Synced / Skipped / Pending outcomes.
- Unchanged bookmarks do not produce unnecessary uploads. Synced includes bookmarks already confirmed and unchanged locally; it is not a count of new database writes.
- Shared Active/Depleted state preserves historical evidence and remains separate from individual Commander reports. There is no automatic regeneration.

## EDMC plugin

- The main section now displays **Alliance Community Deposits**.
- **Status Report → Report Active / Report Depleted** lets authorized Commanders report a community deposit without owning its RhinoSpotter bookmark. Confirmation is required before sending.
- Unconfirmed Status Reports retain their operation UUID for manual retry, including after restarting EDMC.
- Improved System Deposits layout, wrapped messages, compact confirmation dialogs and clearer recovery instructions.
- Small ▲ / ▼ buttons move the entire plugin section and preserve its position after restarting.
- Tracking uses canonical deposit coordinates and validates the current planetary radius, falling back to the canonical radius when needed.

## Finder

- **Alliance Community Deposits** filters use the saved Default Max Ly immediately, with a maximum of **100 Ly**.
- Removed Load All while retaining normal paginated searches.
- Improved native window resizing, maximize/restore and Settings layout; Expand Results remains available.
- Added developer credits, a repository link and the original Mahon logo in the header.
- Community tables no longer display Amount; stored data is retained and Density/Rigs behavior is unchanged.

## Updating from v1.0.4

1. Close Finder and EDMC.
2. Download the Finder EXE and/or EDMC ZIP below.
3. Replace the plugin files inside the existing **EDHF_Community_Navigator** folder. Keep that folder name and do not install a second copy.
4. Preserve settings, Windows credentials, synchronization fingerprints and pending operations. Restart EDMC after replacing the files.
5. Install/select the new Finder EXE separately if using Open Finder from EDMC.

RhinoSpotter is required for Sync Bookmarks, but not for community browsing, tracking or direct Status Reports. A valid Community API key is required. The internal Navigator names and update channel are unchanged.

**Timestamp limitation:** an Active transition without a verifiable newer RhinoSpotter version can be skipped. Automatic removal of Depleted in RhinoSpotter is not treated as a new Active observation; the client does not invent timestamps.

## Downloads and verification

- `ED-Hotspots-Finder-Rings-and-Planets-v1.0.5.exe`
- `Hotspots-Finder-EDMC-Plugin-v1.0.5.zip`
- `SHA256.txt`

```text
2dfd66acf5d36ca29f8b28284c92c0425c64f5f12a04750e726e928d637a40cb  ED-Hotspots-Finder-Rings-and-Planets-v1.0.5.exe
dd981507b20d757888ca9ebc38b0b5391eaab048abc1168b0c597418009c8728  Hotspots-Finder-EDMC-Plugin-v1.0.5.zip
```

Both clients use the stable update channel. Existing v1.0.4 clients recognize v1.0.5 once this release is published as the latest stable release with both assets attached.

---

# v1.0.4 — ED Hotspots Finder - Rings & Planets

### Finder and EDMC

- Adds Community Deposits integration for reading and submitting deposit reports.
- Integrates RhinoSpotter bookmarks with incremental synchronization based on local fingerprints.
- Adds a compact confirmation preview before synchronization, showing new, modified, and unchanged deposit counts.
- Shares one Community Deposits API key between Finder and EDMC through Windows Credential Manager.
- Improves synchronization dialog positioning, lifecycle handling, and EDMC theme consistency.
- Preserves depletion state when comparing and synchronizing bookmark reports.

Community Deposits access requires an authorized API key with both `can_read=1` and `can_write=1`. The key is configured by the user and is not included in these downloads.

### Backend protections

The deployed Community Deposits Worker and D1 schema preserve individual Commander reports alongside shared deposit aggregates. A database-level geographic duplicate guard protects against concurrent inserts for the same nearby deposit, and per-report handling prevents one Commander's report from improperly overwriting shared deposit data. These protections are implemented in the backend; the Finder and EDMC plugin do not provide these guarantees by themselves.

### Installation

- **Finder:** Download and run the Windows executable, then configure an authorized Community Deposits API key.
- **EDMC plugin:** Extract the ZIP into EDMarketConnector's `plugins` folder, preserving the `EDHF_Community_Navigator` directory. Restart EDMC and configure the authorized API key.
- Verify the downloaded files with `SHA256.txt`.

# v1.0.2 — Community Deposits, RhinoSpotter API and EDMC Plugin

This release expands the existing v1.0.2 maintenance update into the first unified **ED Hotspots Finder + Hotspots Finder EDMC Plugin** release.

The desktop Finder and the EDMC plugin share the same Community Deposits service and the same public release version.

## ED Hotspots Finder changes

- Added automatic detection of RhinoSpotter 5.1+ `rs_api.py` from the EDMC plugin folder.
- RhinoSpotter bookmarks are now read through `rs_api.bookmarks()` when available.
- Direct SQLite and legacy JSON access remain compatibility fallbacks for older RhinoSpotter installations.
- Settings reports the detected RhinoSpotter API version and bookmark count.
- Synchronization confirmation and completion dialogs report the actual source used.
- Missing planet radii can be recovered from another bookmark on the same body when available.
- Stable report IDs are preserved so existing Community Deposits reports are updated instead of duplicated.
- RhinoSpotter 5.3/5.4 editable bookmark fields are supported: **Location**, **Material**, **Rigs**, **Amount**, **Density** and depletion state can update an existing synchronized report without creating a duplicate.
- Existing reports created before the RhinoSpotter 5.3/5.4 compatibility update remain compatible with the current identity logic.
- Synchronization now distinguishes **new**, **matched**, **updated** and **unchanged** reports.
- Added local delta synchronization: after the first successful sync, bookmark fingerprints are stored locally and only new or modified bookmarks are sent to Community Deposits.
- Unchanged bookmarks are filtered before the HTTP request, reducing Community Deposits Worker/D1 work on repeated syncs.
- RhinoSpotter bookmark `id` is used as the stable local comparison key when available.
- RhinoSpotter `revision()` is retained as diagnostic metadata but is not used as the sole skip condition; fingerprints remain authoritative so edits are not missed.
- The shared Finder/EDMC sync state is stored in `%APPDATA%\HotspotsFinder\rhinospotter_sync_state.json`.
- Re-synchronizing an unchanged report no longer intentionally advances the deposit's visible **Updated** time on the Community Deposits service.
- Compatibility was verified with RhinoSpotter 5.5.1 using API `SCHEMA = 1`.
- Added the missing **Location** column to Community Deposits results.
- Enabled **Check for updates on startup** and added a direct GitHub repository link in Settings.
- Standardized Community Deposits dialogs on the public application title.
- The Windows release is now distributed directly as the versioned standalone executable instead of wrapping the Finder in an additional ZIP.

## Hotspots Finder EDMC Plugin

v1.0.2 also introduces the first public release of the EDMarketConnector plugin, published as:

```text
Hotspots-Finder-EDMC-Plugin-v1.0.2.zip
```

Main features:

- **Sync Bookmarks** through RhinoSpotter 5.1+ `rs_api.py`.
- Local fingerprint-based delta sync uploads only new or modified RhinoSpotter bookmarks after initialization.
- Finder and EDMC share the same local sync-state file, so either client can continue from the latest successful synchronization state.
- **Scan System** for Community Deposits in the current Elite Dangerous system.
- Cached **Open Deposits** without unnecessary repeat API requests.
- **Refresh Deposits** only when relevant synchronized data changed.
- Results table with Body, Location, Material, Rigs, Amount, Density, Latitude, Longitude, Reports and Updated.
- **Start Tracking** with a compact always-on-top navigation HUD.
- Tracker display of material and RhinoSpotter **Location**.
- **Travel to <system>** when the selected deposit is in another system.
- **Approach body <body>** while surface coordinates are not yet available.
- Altitude-aware target distance during aerial approach.
- Heading-relative direction arrow.
- Independent saved tracker position.
- **Open Finder** directly from EDMC.
- Automatic update check using the same GitHub release channel as the desktop Finder.

The plugin uses the same Community Deposits backend as the desktop application and does not maintain a separate deposit database.

## Distribution

The unified v1.0.2 GitHub Release contains the standalone Finder executable, the EDMC plugin package and shared checksums:

```text
ED-Hotspots-Finder-Rings-and-Planets-v1.0.2.exe
Hotspots-Finder-EDMC-Plugin-v1.0.2.zip
SHA256.txt
```

The public Windows executable remains unsigned, so Windows SmartScreen may display an unknown-publisher warning.

---

# v1.0.1 — RhinoSpotter compatibility update

This maintenance release updates the RhinoSpotter integration for the storage format used by current RhinoSpotter releases.

## Changes

- Added automatic detection of the RhinoSpotter SQLite bookmark database at `%LOCALAPPDATA%\RhinoSpotter\db\rhinospotter.db`.
- Reads the RhinoSpotter database in SQLite read-only mode.
- Preserves support for legacy JSON card folders as a fallback.
- Preserves stable report IDs so previously synchronized bookmarks are updated rather than duplicated.
- Updated Settings to show the detected RhinoSpotter source and bookmark count.
- Updated the upload confirmation and completion summary to use bookmark/database terminology.
- Improved Settings window initialization so it opens already rendered instead of exposing intermediate layout states.
- Updated RhinoSpotter and Community Deposits documentation for the current workflow.

The integration was tested with newly created RhinoSpotter 4.4.3 bookmarks as well as previously migrated records.

---

# v1.0.0 — First public Windows release

This is the **first public release** of **ED Hotspots Finder - Rings & Planets**.

The project went through several internal development iterations before release; those internal version labels are not part of the public release history. Public versioning therefore starts at **v1.0.0**.

ED Hotspots Finder is built around **multi-system search and filtering**, with a particular focus on finding systems that satisfy the strategic and physical requirements of **Powerplay-oriented research**.

## Highlights

- Standalone Windows interface.
- Manual **System Input** with Spansh-backed system-name normalization before scanning.
- **System Filters** for Faction, Powerplay power, Power States, Reference System and distance.
- Search large candidate groups for the ring, hotspot and planetary characteristics required by a task.
- Hotspot searches with ring/mineral filters and **Only Pristine**.
- Planet searches with body-type filters, **Only Landables**, volcanism and arrival-distance data where available.
- Integrated **Community Deposits** results from the ED Alliance Community Deposits service.
- Optional RhinoSpotter synchronization for contributing compatible local discoveries to the shared database.
- Local result tables with sorting/filtering.
- Export of the current result tab to **CSV** and **XLSX**.
- Expand/Restore results view and detailed activity log.
- Themes: **Deep Black** and **Green Warm**.
- UI Scale options: 100%, 110%, 115% and 125%, with 115% as the default.
- Startup splash and first-window reveal handling designed to avoid visible initialization flicker on Windows.
- Application icon and Windows executable metadata prepared for the first public release.

## Search behavior

Manual system names are canonicalized through the same Spansh lookup used by Reference System. For example, differently cased inputs such as `mehit`, `wuRANgo` or `SEEDI` are resolved to the canonical names before the scan proceeds.

Duplicates are removed after canonicalization.

The same workflow can also begin from System Filters, allowing commanders to define a Powerplay, faction or distance-based search area before checking the resulting systems for the required hotspot, ring and planetary characteristics.

## Community Deposits and RhinoSpotter

The desktop app can query the **ED Alliance Community Deposits** service and display known player-reported surface deposits.

The long-term goal is to build a useful shared database of planetary deposits from discoveries contributed by the community.

The current release includes optional synchronization of compatible local RhinoSpotter records with Community Deposits. RhinoSpotter is an independent EDMC project developed by **Fumlop**:

https://github.com/Fumlop/EDRhinoSpotter

See the repository documentation for more information about Community Deposits and the current RhinoSpotter workflow.

## Local settings

The application stores its settings in:

```text
%APPDATA%\HotspotsFinder\config.json
```

## Export

Results can be exported locally:

- CSV: UTF-8 with BOM and semicolon delimiter.
- XLSX: locally generated workbook with frozen headers and autofilter.

## Windows build

The first public release uses Windows version metadata **1.0.0.0**.

The repository still contains internal source/build filenames using `v8` because that was the final development iteration before the public `v1.0.0` release. Those internal labels do not indicate previous public releases.

The Windows build uses:

- entry point: `hotspots_finder_gui_v8_final.py`
- PyInstaller spec: `HotspotsFinder-v8.spec`
- icon: `app.ico`
- splash: `ED_Hotspots_Finder.png`
- public version metadata: `1.0.0.0`
- executable name: `ED Hotspots Finder - Rings & Planets.exe`

The public Windows executable is currently unsigned, so Windows SmartScreen may display an unknown-publisher warning.

## Notes

Spansh and Community Deposits are community-data sources. Missing or outdated source data can affect search results.
