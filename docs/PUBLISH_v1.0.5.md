# v1.0.5 stable — publication procedure

Prepared locally on 16 November 2026. No staging, commit, push, tag or GitHub release action has been executed. Application code, internal Navigator identifiers and backend are unchanged by this preparation.

## Verified state

- Branch: main. Local HEAD and remote main both fbe211b53f01e220b7cca16f34a9b17342d407bc at preparation time.
- Origin: https://github.com/LittleJacket99/ED-Hotspots-Finder-Rings-and-Planets-with-EDMC-plugin.git.
- No local/remote v1.0.5 tag or GitHub release/draft at preparation time. GitHub CLI authentication check passed; do not print tokens.
- Index initially empty. Eleven required runtime/packaging files are still untracked; they are explicitly included in docs/RELEASE_v1.0.5_FILES.txt. They become tracked during the authorized staging step below. There are 87 total intended source/test/public-documentation paths in that list, including already tracked unchanged files.
- 24 Finder modules, 20 EDMC modules, 11 shared modules and three graphics resources present. Stable manifest/version 1.0.5; Windows metadata 1.0.5.0 without prerelease flag.
- Final artifact hashes match SHA256.txt; ZIP is CRC-valid, has exactly 22 files and matches the current plugin sources. The EXE was not rebuilt or changed by publication preparation.
- In-game verification PASS reported by the user. Prior source suite: 191/191 PASS. Packaging/display checks were rerun after the last change (26/26 PASS); packaged updater checks passed for both old/new clients.

## Exclusions

Do not use git add . or git add -A. Use only the explicit source allowlist. Do not force-add release artifacts: the EXE, ZIP and SHA256.txt are GitHub Release assets, not repository content. Existing .gitignore excludes release/, build/dist directories, .venv, caches and known credential files. The four local diagnostic reports containing machine-specific paths are now ignored individually; they remain on disk. Smoke fixtures, guards, profiles, logs, backups and exports stay outside the commit. No credential-like literals or absolute personal Windows paths were found by the scoped check of intended text inputs; this is not a full Git-history secret audit.

Do not change EDHF_Community_Navigator folder/internal identifiers. The EDMC heading is Alliance Community Deposits and the asset remains Hotspots-Finder-EDMC-Plugin-v1.0.5.zip.

## Residual verification (non-blocking by user decision)

- Read-only write rejection: NOT TESTED in production; requires an existing authorized Read-only credential.
- Authentic Status Report creation: PASS from the user's two real observations. Same-UUID retry / lost receipt: NOT TESTED in production. Local idempotency tests passed; no new test event should be invented. The same-UUID retry remains a separate controlled test if authorized.
- The next live updater discovery check requires the release to be publicly available. Offline tests confirm both v1.0.4 packaged checkers recognize v1.0.5 and asset names match.

## Exact future commands — require explicit authorization before execution

Run PowerShell from the repository root. Each numbered step is a checkpoint, not permission to continue after an error.

### 1. Preflight and checksums

```powershell
$ErrorActionPreference = 'Stop'
$GitHubRepo = 'LittleJacket99/ED-Hotspots-Finder-Rings-and-Planets-with-EDMC-plugin'
$Tag = 'v1.0.5'
if ((git branch --show-current).Trim() -ne 'main') { throw 'Unexpected branch.' }
if ((git remote get-url origin).Trim() -ne "https://github.com/$GitHubRepo.git") { throw 'Unexpected origin.' }
if (git diff --cached --name-only) { throw 'Review existing staged work first.' }
$LocalHead = (git rev-parse HEAD).Trim()
$RemoteMain = git ls-remote origin refs/heads/main
if ($LASTEXITCODE -ne 0 -or -not $RemoteMain) { throw 'Remote preflight failed.' }
if (($RemoteMain -split '\s+')[0] -ne $LocalHead) { throw 'Remote main changed: stop, no force push.' }
$RemoteTag = git ls-remote origin refs/tags/v1.0.5
if ($LASTEXITCODE -ne 0) { throw 'Remote tag check failed.' }
if ($RemoteTag -or (git tag --list v1.0.5)) { throw 'Tag already exists: inspect before proceeding.' }
gh auth status --active
if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication unavailable; do not renew automatically.' }
$ExistingReleasesJson = gh release list --repo $GitHubRepo --limit 100 --json tagName
if ($LASTEXITCODE -ne 0) { throw 'Release listing failed.' }
if (($ExistingReleasesJson | ConvertFrom-Json) | Where-Object { $_.tagName -eq $Tag }) { throw 'Release/draft already exists.' }
$Assets = @(
  'release/v1.0.5/ED-Hotspots-Finder-Rings-and-Planets-v1.0.5.exe',
  'release/v1.0.5/Hotspots-Finder-EDMC-Plugin-v1.0.5.zip',
  'release/v1.0.5/SHA256.txt'
)
$Expected = @{
  'ED-Hotspots-Finder-Rings-and-Planets-v1.0.5.exe' = '2dfd66acf5d36ca29f8b28284c92c0425c64f5f12a04750e726e928d637a40cb'
  'Hotspots-Finder-EDMC-Plugin-v1.0.5.zip' = 'dd981507b20d757888ca9ebc38b0b5391eaab048abc1168b0c597418009c8728'
}
foreach ($Asset in $Assets[0..1]) {
  $Sha = [Security.Cryptography.SHA256]::Create()
  try { $Actual = [BitConverter]::ToString($Sha.ComputeHash([IO.File]::ReadAllBytes((Join-Path $PWD $Asset)))).Replace('-', '').ToLowerInvariant() }
  finally { $Sha.Dispose() }
  if ($Actual -ne $Expected[[IO.Path]::GetFileName($Asset)]) { throw 'Artifact checksum mismatch.' }
}
```

### 2. Stage only the reviewed source inventory, then inspect

```powershell
$Files = Get-Content -LiteralPath 'docs/RELEASE_v1.0.5_FILES.txt'
foreach ($File in $Files) { if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { throw "Missing file: $File" } }
git add --pathspec-from-file=docs/RELEASE_v1.0.5_FILES.txt
if ($LASTEXITCODE -ne 0) { throw 'Staging failed.' }
$Unexpected = @(git diff --cached --name-only | Where-Object { $_ -notin $Files })
if ($Unexpected.Count) { throw 'Unexpected staged files: review before committing.' }
$Tracked = @(git ls-files)
$UntrackedRequired = @($Files | Where-Object { $_ -notin $Tracked })
if ($UntrackedRequired.Count) { throw 'Required files are still untracked.' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged whitespace check failed.' }
git diff --cached --stat
git diff --cached
# Review source/docs changes and confirm that no secrets/personal reports are staged.
```

### 3. Commit and push main

```powershell
git commit -m "Release v1.0.5 stable"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
$ReleaseCommit = (git rev-parse HEAD).Trim()
git push origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed: stop before tag/release.' }
$PushedMain = git ls-remote origin refs/heads/main
if ($LASTEXITCODE -ne 0 -or ($PushedMain -split '\s+')[0] -ne $ReleaseCommit) { throw 'Remote commit not confirmed.' }
```

### 4. Annotated tag, then push only that tag

```powershell
git tag -a v1.0.5 -m "ED Hotspots Finder and EDMC v1.0.5 stable" $ReleaseCommit
if ($LASTEXITCODE -ne 0) { throw 'Tag creation failed; do not force/recreate.' }
git push origin refs/tags/v1.0.5
if ($LASTEXITCODE -ne 0) { throw 'Tag push failed: stop before release.' }
$PushedTag = git ls-remote origin 'refs/tags/v1.0.5^{}'
if ($LASTEXITCODE -ne 0 -or ($PushedTag -split '\s+')[0] -ne $ReleaseCommit) { throw 'Remote tag target not confirmed.' }
```

### 5. Create a draft with exactly three assets

```powershell
gh release create v1.0.5 @Assets --repo $GitHubRepo --verify-tag --draft --title 'ED Hotspots Finder + EDMC v1.0.5' --notes-file 'docs/RELEASE_v1.0.5_GITHUB_NOTES.md'
if ($LASTEXITCODE -ne 0) { throw 'Draft creation/upload failed: inspect actual state, do not retry blindly.' }
gh release view v1.0.5 --repo $GitHubRepo --json tagName,isDraft,isPrerelease,assets,url
```

Verify the tag, notes, isDraft=true, isPrerelease=false and all three exact asset names. Review the draft and uploaded checksums before the public step. Do not use --generate-notes or upload old builds.

### 6. Publish the reviewed draft as latest stable

This is the final public action and must be covered by explicit user authorization.

```powershell
gh release edit v1.0.5 --repo $GitHubRepo --verify-tag --draft=false --prerelease=false --latest
if ($LASTEXITCODE -ne 0) { throw 'Publication result uncertain: inspect release state before any retry.' }
gh release view v1.0.5 --repo $GitHubRepo --json tagName,isDraft,isPrerelease,assets,url
```

Success: isDraft=false, isPrerelease=false, latest stable v1.0.5 with all three assets. Then verify latest-stable updater discovery and download checksums without Sync/Status Report. Do not run any backend/database operation.

## Stop conditions

Unexpected remote changes, an existing tag/release, missing or unexpected staged files, secret/personal content, checksum mismatch, authentication failures, missing assets or any uncertain command result: stop and inspect. No force pushes, tag replacements, automatic rollback, rebuild or publication retry.

READY for the above sequence after explicit authorization. Staging/commit/publication remain unexecuted; all eleven untracked required files are covered by the checked staging inventory.

Preparation verification: staging dry-run PASS (67 changed/added files from the 87-path allowlist), index unchanged/empty, all seven explicitly checked local-report/artifact paths ignored, artifact checksums PASS, release-preparation tests 17/17 PASS. New public documentation contains no absolute personal Windows paths.
