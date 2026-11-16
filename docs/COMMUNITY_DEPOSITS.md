# Alliance Community Deposits — v1.0.5

Community Deposits is a shared catalog of planetary surface deposits. Access is restricted to authorized users with a valid API key. Read permits browsing and tracking; Write permits contribution and direct status reports. Finder and EDMC share Commander-specific Windows Credential Manager storage. Credentials are never included in downloads.

## Finder

**Alliance Community Deposits** uses normal paginated searches and existing filters. There is no Load All button. Default Max Ly initializes the filter from Settings and a changed default applies immediately; a manual filter edit does not save a preference. Valid values are finite, positive and at most **100 Ly**. Legacy larger defaults are clamped safely; other invalid defaults fall back to 50.

Community results show Rigs, Density and compact Status; Amount remains in the API/database but is hidden. The window supports native resize/maximize/restore, with fixed filters and variable results width. Expand Results explicitly hides/restores filters and horizontal scrolling remains available. The minimum width is half the initial width; minimum height retains access to the fixed filters. Small screens can be constrained by this scaled minimum. Settings includes developer credit/repository link; the header uses the original transparent Mahon logo.

## EDMC

Scan System reads all pages for the current system. Open Deposits uses its cache and Refresh Deposits refreshes stale data. System Deposits offers canonical-coordinate Start Tracking and **Status Report → Report Active / Report Depleted**. Direct reports require Write and confirmation, but no bookmark. The whole section can be moved using ▲ ▼ and its position is retained.

## Contribution and outcomes

Finder's Upload RhinoSpotter Deposits and EDMC's Sync Bookmarks read local bookmarks, compare stable fingerprints and request confirmation. HTTP uploads contain no more than **five reports** per batch. Each item is authorized and handled independently; successful fingerprints survive partial failures. Unchanged content and timestamp-only changes do not cause new writes.

- **Synced:** a confirmed contribution, including locally unchanged confirmed content.
- **Skipped:** a known invalid/stale/unverifiable source version. Edit or re-mark when appropriate; identical retries cannot resolve it.
- **Pending:** authentication, temporary or uncertain results. Correct the key or wait as directed and manually retry through the original Sync button.

HTTP 429 stops further sends for that Commander. There is no automatic retry queue. Lost Status Report receipts use the separate **Retry pending Status Report** menu, keeping their original UUID across restarts. Deliberate new confirmations create new events. API key changes refresh cached permissions without restart.

## Individual snapshots and shared Active/Depleted

All individual Commander reports remain separate. Original marked_at, updated_at and depletion values are retained. A strictly newer valid depletion can update only depletion without a newer updated_at when all other content and technical fields are unchanged. Old source versions cannot overwrite later report state. An unversioned Active transition is rejected and reported as Skipped.

Shared state is selected independently from retained valid depletion evidence and explicit direct-event recorded_at. A later direct Active report can supersede depletion; a later depletion can supersede Active. Equal conflicting times choose Depleted and expose conflict metadata. updated_at, marked_at, Sync/reception time and an Active snapshot are not automatic proof of a new shared Active observation.

The immutable legacy baseline preserves historical Active, complete Depleted and date-only references, including incomplete attribution. Clearing an individual snapshot does not erase its retained depletion. No automatic 40-day regeneration or other timed reactivation is introduced. Rigs/Density are not reselected in v1.0.5; Amount remains stored.

Status shows Active, or Depleted with UTC calendar-day age for a precise valid timestamp. For a partial historical date it shows the date itself. This age is not a claim of uninterrupted physical depletion. Source, exact reference, conflict and latest direct-event metadata remain in API data.

## Geographic matching and tracking

Canonical system/body/coordinates and planet radius drive shared-deposit tracking. Nearby matching within 100 metres and concurrent duplicate protections remain. Missing technical metadata can only be completed under the existing ownership guards; existing shared metadata cannot be arbitrarily replaced by another Commander. Incomplete individual historical reports do not replace canonical tracker coordinates.

## Stable distribution

v1.0.5 is prepared for stable distribution. Install the desktop EXE and/or EDMC ZIP when published. Backend v1.0.5 and migrations 0004/0005 are already deployed and verified; client installation does not run migrations. Legacy importer/uploader tools are unsupported. See [RhinoSpotter integration](RHINOSPOTTER.md) and [EDMC guide](EDMC_COMPANION.md).
