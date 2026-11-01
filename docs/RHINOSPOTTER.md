# RhinoSpotter integration

**ED Hotspots Finder - Rings & Planets** and the **Hotspots Finder EDMC Plugin** integrate with **[RhinoSpotter](https://github.com/Fumlop/EDRhinoSpotter)**, an independent EDMC plugin developed by **Fumlop** for Elite Dangerous surface mining.

RhinoSpotter and this project are separate projects with complementary roles.

## What RhinoSpotter does

RhinoSpotter helps commanders record planetary surface-mining locations while playing Elite Dangerous.

Compatible bookmarks can include information such as:

- system and body;
- RhinoSpotter Location;
- material;
- Rigs;
- Amount;
- Density;
- latitude and longitude;
- heading;
- planet radius and other available body metadata;
- depletion information.

ED Hotspots Finder and the EDMC Plugin do not replace RhinoSpotter's in-game recording workflow. They use compatible RhinoSpotter bookmarks as a contribution source for **Community Deposits**.

## Why the integration exists

The purpose of the integration is to help build the shared Community Deposits database.

The intended workflow is:

**RhinoSpotter records a discovery → Finder or EDMC Plugin synchronizes it → Community Deposits makes it searchable**

This lets local discoveries made by individual commanders contribute to a larger shared dataset.

## RhinoSpotter 5.1+ external API

Current RhinoSpotter releases expose a documented external API through:

```text
%LOCALAPPDATA%\EDMarketConnector\plugins\RhinoSpotter\rs_api.py
```

The integration uses `rs_api.bookmarks()` and reads `rs_api.revision()` as synchronization metadata. It currently supports RhinoSpotter API `SCHEMA = 1`.

Using the documented API avoids depending on RhinoSpotter's private storage implementation. Compatibility has been verified with RhinoSpotter 5.5.1.

## ED Hotspots Finder behavior

The desktop Finder automatically prefers `rs_api.py` when it is available.

For older RhinoSpotter installations, the Finder retains compatibility fallbacks for:

- the local SQLite bookmark database, opened read-only;
- legacy JSON card folders.

A custom RhinoSpotter source can be selected in Finder Settings. The Settings status can show the detected source, RhinoSpotter API version when applicable, and bookmark count.

When synchronization is started, compatible bookmarks are validated and prepared before being sent to Community Deposits.

The completion summary reports values such as:

- bookmarks found;
- valid records;
- locally unchanged/skipped bookmarks;
- bookmarks sent;
- new deposits;
- reports matched to existing deposits;
- updated reports;
- server-unchanged reports;
- errors.

## EDMC Plugin behavior

The **Hotspots Finder EDMC Plugin** intentionally uses RhinoSpotter 5.1+ `rs_api.py` only.

Use **Sync Bookmarks** inside EDMC to send compatible bookmarks to Community Deposits.

RhinoSpotter is not required for the plugin's Community Deposits lookup or navigation features. If RhinoSpotter is missing or too old, only bookmark synchronization is unavailable.

## Delta synchronization

Finder and EDMC keep a shared local synchronization state at:

```text
%APPDATA%\HotspotsFinder\rhinospotter_sync_state.json
```

On the first successful synchronization, compatible bookmarks are sent normally and a fingerprint is saved for each stable RhinoSpotter bookmark ID.

On later synchronizations, the clients still read the local RhinoSpotter bookmarks but compare them locally first. Only bookmarks whose fingerprint is new or different are sent to Community Deposits. Unchanged bookmarks therefore cause no Community Deposits POST and no per-report D1 matching work.

### Community Deposits API credentials

Both clients use the same `Authorization: Bearer <API key>` credential for GET and POST/batch requests. Configure one key with both `can_read=1` and `can_write=1` for a commander in Finder Settings or the EDMC plugin; the key must be provisioned externally. Finder and EDMC store and read it through the same commander-specific Windows Credential Manager target. The key is visible in the UI and is never written to EDMC preferences, Finder JSON settings, logs, sync state, or release artifacts. Finder settings persist only the selected commander name.

The API permits reads across the shared deposit collection. The commander on every submitted bookmark must match the key's commander (case-insensitive after trimming). The Worker remains the authority and rejects a mismatch with HTTP 403.

Batch responses are checked for `status: "ok"`, the exact `received` count, one result per submitted `report_id`, unique IDs, boolean `ok`, and a recognized success `action` (`inserted`, `matched_existing_deposit`, `updated_report`, or `unchanged`). An item with `ok: false` is left eligible for retry. Structurally incomplete or inconsistent responses do not mark records synchronized.

Clients preserve the source field's three depletion states: an absent `depleted_at` stays omitted, explicit JSON `null` stays null, and a timestamp stays a timestamp. The API treats omission on update as “leave depletion unchanged” and explicit null as “clear depletion.” The client does not synthesize null for a missing field.

Finder and EDMC serialize the complete bookmark state read, fingerprint comparison, HTTP upload and state save with the same named Windows mutex. If a process terminates while holding the mutex, Windows marks it abandoned and another client can acquire it and continue. A second sync can wait up to the mutex acquisition timeout before reporting that the shared sync is still in progress.

Abandoning the mutex does not cancel an HTTP request that the client has already sent to the Worker. The Worker may continue processing that request after the client process has terminated. In this scenario, a client-side mutex cannot guarantee the ordering of remote writes: an earlier request may still be processed after another client has acquired the abandoned mutex and sent a later write. Guaranteeing remote write order requires support on the Worker, such as report versions or conditional writes.

`rs_api.revision()` is recorded as useful metadata, but it is not trusted as the sole condition for skipping bookmark reads. The current RhinoSpotter 5.5.1 implementation derives that value from aggregate database values rather than a complete per-row content hash, so a bookmark edit can leave the revision unchanged. Stable-ID fingerprints are therefore the authoritative change detector.

If writing the local sync-state file fails, the server synchronization result is not discarded; a later sync may simply resend records that could not be cached locally. Server-side stable report identity keeps that retry safe.

Deleting a RhinoSpotter bookmark removes it from the local comparison state on the next successful sync, but does not by itself delete an already shared Community Deposits report.

## Stable report identity

The integration generates a stable `report_id` from fields that identify the bookmark/deposit rather than mutable state.

RhinoSpotter's stable bookmark identity is preserved by current clients. Editable values such as **Location**, **Material**, **Rigs**, **Amount**, **Density**, `updated_at` and depletion timestamps do not deliberately create a new report identity when the same bookmark is edited.

This allows the same RhinoSpotter bookmark to update its existing Community Deposits report instead of creating a duplicate.

## Mutable deposit data

Current Community Deposits behavior treats these RhinoSpotter changes as meaningful updates:

- **Location**;
- **Material**;
- **Rigs**;
- **Amount**;
- **Density**;
- depletion state.

Re-synchronizing the same values again returns `unchanged` and does not intentionally refresh the visible **Updated** timestamp.

## Location

RhinoSpotter's bookmark `location` value is mapped to Community Deposits `location_index`.

It is displayed as **Location** in both Finder and EDMC Plugin results, and it is also shown in the EDMC navigation HUD.

## Using RhinoSpotter with the Finder

1. Install RhinoSpotter 5.1+ as an EDMC plugin.
2. Record planetary deposits while playing.
3. Open ED Hotspots Finder.
4. Verify the detected RhinoSpotter source in Settings.
5. Run the synchronization workflow.
6. Search Community Deposits together with other Finder results.

## Using RhinoSpotter with the EDMC Plugin

1. Install RhinoSpotter 5.1+ and the Hotspots Finder EDMC Plugin.
2. Record bookmarks normally in RhinoSpotter.
3. Press **Sync Bookmarks** in Hotspots Finder Deposits Companion.
4. Use **Scan System** / **Open Deposits** to inspect Community Deposits for the current system.
5. Select a deposit and press **Start Tracking** when navigation is useful.

## Project credit

RhinoSpotter is developed and maintained independently by **Fumlop**.

Project repository:

**https://github.com/Fumlop/EDRhinoSpotter**

RhinoSpotter is not bundled with this project, and this project does not claim ownership of RhinoSpotter or its code.

## Community Deposits

For more information about the shared database and how contributions are used, see [Community Deposits](COMMUNITY_DEPOSITS.md).
