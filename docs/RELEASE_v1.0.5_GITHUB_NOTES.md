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
