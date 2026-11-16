# RhinoSpotter integration — v1.0.5

RhinoSpotter is independently developed by **Fumlop**: https://github.com/Fumlop/EDRhinoSpotter. It is not bundled, modified or owned by this project. Install it separately for bookmark synchronization; community browsing/tracking/direct EDMC reporting do not require a bookmark.

## Sources and timestamps

EDMC reads the documented `rs_api.py` API (SCHEMA 1). Finder prefers that API and retains read-only SQLite/legacy JSON fallback for older installations. RhinoSpotter 6.6.0 exposes updated_at in bookmarks:

- marked_at: original marking time.
- updated_at: last Edit or Re-mark; None if never edited.
- Tons mined, Mark depleted and automatic removal of Depleted after 40 days do not necessarily update updated_at.

Both mappings/serializers preserve available timestamps, including a space separator and six fractional digits. None is not replaced with a Sync clock. Report identity stays stable; no artificial version or observation time is generated.

## Sync and credentials

Use Finder Settings or EDMC Configure Community API Keys to store a Commander-specific key in Windows Credential Manager. The input is masked. Read permits community catalog access; Write permits bookmark contributions and direct EDMC events. To use both, configure a key with both permissions. The Worker verifies the key and Commander. Switching keys invalidates old cached permissions and responses without restarting.

Finder uses Upload RhinoSpotter Deposits; EDMC uses Sync Bookmarks. Preview and confirmation remain mandatory. Stable-ID content fingerprints are the change detector; revision() is metadata, not the sole detector. A change only to updated_at does not trigger an upload. Technical completion and genuine content/depletion changes are considered separately.

Requests contain at most five reports. Readers follow all authenticated pages. Synced means confirmed or previously confirmed unchanged. Skipped means a definite source-version/validation refusal; a real source edit/version can make it eligible again. Pending means a recoverable or uncertain outcome; manually use the same Sync button after fixing credentials, waiting for 429 backoff or restoring connectivity. Partial successes are retained. No automatic resend queue exists.

Finder and EDMC retain the existing shared sync-state file and named mutex. Existing v1.0.4 configuration/fingerprints are retained; no blanket reset is required. S2 and atomic Worker guards protect concurrent/obsolete writes; the client mutex alone does not guarantee remote ordering after a lost response. Deleting a local bookmark does not delete a shared report.

## Depletion and shared state

Individual report updates normally need a real increasing updated_at. A strictly newer valid depleted_at can authorize only a depletion change when other effective content/technical fields are unchanged. Retries return unchanged without redundant report UPDATEs. Older restored depletion/recheck dates cannot overwrite a newer known depletion.

Clearing depletion without a verifiable newer version is not forced. It is Skipped with ACTIVE_TRANSITION_UNVERIFIABLE or STALE_UPDATE; the server state remains protected. RhinoSpotter's automatic 40-day clearing is not a new Active observation. No timestamp is invented to bypass this rule.

Shared state is separate from individual snapshots. It uses retained depletion evidence and explicit EDMC Status Report events, preserving legacy baseline and original timestamps. Neither an Edit/Re-mark nor updated_at alone establishes a new shared Active observation. There is no automatic regeneration in Community Deposits. A deliberate direct EDMC Active/Depleted report is recorded at database UTC time after confirmation and can be made without a bookmark.

Direct-event retry is separate: Status Report → Retry pending Status Report keeps the original UUID and timestamp through receipt loss/restart. Normal Sync never retries that operation.

## Installation and updates

Install the v1.0.5 stable packages when published; keep the EDHF_Community_Navigator folder name, settings, credential targets, fingerprints and pending files. Stable-channel update checks detect v1.0.5 from v1.0.4. Legacy backend import/uploader tools are unsupported; Finder retains rhinospotter_sync.py and rhinospotter_sync_service.py.

See [Community Deposits](COMMUNITY_DEPOSITS.md) for catalog/state semantics and [EDMC Companion](EDMC_COMPANION.md) for commands.
