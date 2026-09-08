# Release Tool

CLI tool for releasing software via FTP, plus a `create` subcommand that runs a
project's whole release in one command.

## Installation

```bash
uv sync
```

## Usage

```bash
# Basic usage
release-tool myapp.exe config.ini

# With previous version for backup naming
release-tool myapp.zip config.ini --previous-version 1.9.5

# Preview without changes
release-tool dist/app.exe release.ini --dry-run

# Verbose output (debug logging)
release-tool myapp.exe config.ini --verbose
```

## Options

| Option | Description |
|--------|-------------|
| `--previous-version`, `-p` | Previous version string for backup folder naming (e.g., '1.0.0'). Used with `subfolder_naming = version`. If the version folder already exists, prompts to abort or overwrite. |
| `--dry-run` | Preview changes without uploading or modifying files |
| `--verbose` | Enable debug logging to trace FTP operations, file checks, and directory creation |

## Configuration

Create an INI configuration file:

```ini
[FTP]
host = ftp.example.com
port = 21
username = deploy_user
password = your_password
remote_path = /releases/myapp

[OldFileHandling]
; Policy: "delete" or "rename"
policy = rename
; Subfolder for backups (when policy = rename)
subfolder_base = old_versions
; Naming: "timestamp" (YYYYMMDD_HHMMSS) or "version" (uses --previous-version arg)
subfolder_naming = timestamp

[PreSigning]
; Enable pre-signing workflow (default: false)
enabled = true
; Network path where signing service monitors for files
network_path = \\SERVER\Signing
; Network path where signed files are placed by the signing service
network_path_signed = \\SERVER\Signing\signed
; Expected signer name to verify (CN field from certificate)
expected_signer = Your Company Name
; Poll interval in seconds (default: 10)
poll_interval = 10
; Timeout in seconds (default: 300 = 5 minutes)
timeout = 300

[ReleaseNotes]
; Local path to release notes folder containing version subfolders (e.g., 1.0.0/, 1.0.1/)
path = D:/Projects/MyApp/release_notes
; Remote FTP path where release notes should be uploaded
remote_path = /public/sites/myapp/release_notes
```

### Pre-Signing Workflow

When `[PreSigning]` is enabled, the tool performs these steps before FTP upload:

1. Copies the executable to `network_path`
2. Waits for the signed file to appear in `network_path_signed`
3. Verifies the digital signature matches `expected_signer`
4. Moves the signed file back to the original location
5. Cleans up files from both network paths
6. Proceeds with FTP upload

This integrates with code signing services that monitor a network folder for files to sign and output signed files to a separate directory.

### Release Notes Upload

When `[ReleaseNotes]` is configured, the tool automatically uploads new release notes folders after the main file upload:

1. Scans the local `path` for version folders (e.g., `1.0.0/`, `1.0.1/`)
2. Compares against existing folders on the remote `remote_path`
3. Uploads only new version folders and their contents
4. Existing folders are skipped

This allows you to maintain release notes locally and have them automatically synced during releases.

## Create a release (`create` subcommand)

The `create` subcommand orchestrates a full release for a project by sequencing
that project's existing batch files, git, and (only when release notes are
missing) a headless Codex call. Run it from the project root:

```bash
# End-user release: label, notes, build, translate, publish prompt, commit, tag
release-tool create

# Point at a specific config (default: release_create.ini in the cwd)
release-tool create release_create.ini

# Internal test build: skip release notes, tag as INTERNAL
release-tool create --internal

# Preview the resolved label and every command without executing anything
release-tool create --dry-run
```

### What it does

1. **Compute the next label** — `<version>_<build+1>` (build first, ship next).
   Set `versioning = semver` to bump the version's last segment instead of a
   build counter (e.g. `0.1.6` → `0.1.7`) — see
   [`docs/CREATE_RELEASE_COMMAND.md`](docs/CREATE_RELEASE_COMMAND.md#versioning-modes).
2. **Ensure release notes** (skipped with `--internal`) — if `en.json` is missing
   for the shipping label, author it headlessly via
   `codex exec --dangerously-bypass-approvals-and-sandbox`; abort if it still
   doesn't appear.
3. **Bump the build**, then **translate** (unless `english_only`), then **build**.
   If build fails, the build counter is rolled back automatically. Set
   `build_self_contained = true` when the project's `build` bat already does its
   own bump/translate/rollback (a monolithic release script) — `create` then only
   reads `version_get`/`build_get` for the label and just calls `build`.
4. **Publish** — one interactive gate per configured channel. `publish` (and
   `publish_platform`) can be a comma-separated list to gate several targets from
   the same release, e.g. a website upload and a Play Store upload
   (`Publish <label> to <platform>? [y/N]` per channel). Decline a channel to skip
   it; declining/omitting all of them stops after the build (no commit, no tag).
5. **Commit + tag** — `RELEASE (<scope>): <label>` (or `INTERNAL (...)`).
6. **GitHub Release** (optional gate, only after step 5 runs) — with a
   `[GitHubRelease]` section enabled, asks to create a GitHub Release for the
   just-pushed tag and upload its assets. See "Publish a GitHub Release" below.

### `release_create.ini`

Only per-project differences need to be set; everything else uses conventional
defaults (see `examples/release_create.ini`):

```ini
[Release]
scope = app                          ; commit scope
publish_platform = Google Play Store ; named in the publish prompt (comma-list for multiple channels)
; notes_dir = release_notes          ; optional overrides shown with defaults
; en_file = en.json
; label_format = {version}_{build}
; notes_label_format = {version}_{build}  ; defaults to label_format; set when the notes folder must differ
; versioning = build                      ; build (counter) or semver (bump version's last segment)
; english_only = false
; build_self_contained = false       ; true => build bat owns bump/translate/rollback itself

[Bats]
; All paths relative to the project root; omit a line to keep the default.
; version_get / build_get / build_increment / build_decrement / translate / build
; publish has NO default — set it to enable publish + commit + tag, omit to build-and-stop.
; Comma-separate for multiple gated channels, paired by position with publish_platform.
publish = tools/publish_release.bat
```

The legacy publish invocation (`release-tool <file> <config> ...`) is unchanged
and continues to work exactly as before.

## Publish a GitHub Release (`github-release` subcommand)

Creates a GitHub Release for an existing tag and attaches asset files, via the
`gh` CLI (`gh auth login` once, no other runtime dependency). See
[`docs/GITHUB_RELEASE_COMMAND.md`](docs/GITHUB_RELEASE_COMMAND.md) for full usage.

```bash
release-tool github-release v1.7.5 target\fmanSetup.exe \
    --repo OWNER/NAME --notes-json release_notes\1.7.5_3\en.json
```

Re-running against a tag that already has a release re-uploads the assets
(`gh release upload ... --clobber`) instead of failing. It's also available as an
opt-in gate inside `create` via a `[GitHubRelease]` section in `release_create.ini`
(`enabled`, `assets`, `repo`, `tag_format`, `title_format` — see
`examples/release_create.ini`).

## Build and upload an Android APK (`android` subcommand)

Bumps the build number in `pubspec.yaml`, runs the Flutter build, verifies the
APK, and uploads it under a fixed remote name so the download URL never changes.
Replaces the per-project bat chains and their bundled `rclone.exe`. See
[`docs/ANDROID_COMMAND.md`](docs/ANDROID_COMMAND.md) for full usage.

```bash
# Release build: bump, build, verify, upload
release-tool android tools\android_release.ini --project-root .

# Debug build: no bump, uploads as <name>-debug.apk
release-tool android tools\android_release.ini --project-root . --debug
```

If the build fails, the bump is rolled back. Configuration reuses the `[FTP]` and
`[OldFileHandling]` sections above plus an optional `[Build]` section — see
`examples/android_release.ini`.

Not just Flutter: `version_file_format` selects where the build number lives —
`pubspec` (default), `gradle_kts`, `gradle_groovy` or `toml` — so Gradle projects
bump their `versionCode` the same way.

Seven projects have been migrated off their bundled `rclone.exe` bat chains —
see [`docs/ANDROID_MIGRATION.md`](docs/ANDROID_MIGRATION.md) for their configs
and the behavior changes involved.

The build-number bump is also available on its own, for projects that build
through another script:

```bash
release-tool bump-build ..\pubspec.yaml              # 1.0.0+2 -> 1.0.0+3
release-tool bump-build ..\pubspec.yaml --decrement  # rollback
```

## Upload a directory tree (`sync` subcommand)

Mirrors a local directory to an FTP remote, creating remote directories as
needed — the replacement for the `rclone copy <dir> ftp-remote:` bat calls, and
the last thing that kept a bundled `rclone.exe` around. See
[`docs/SYNC_COMMAND.md`](docs/SYNC_COMMAND.md) for full usage.

```bash
release-tool sync tools\sync_releases.ini --project-root .

# List what would be uploaded, without connecting
release-tool sync tools\sync_releases.ini --project-root . --dry-run
```

Configuration reuses the `[FTP]` section above plus a `[Sync]` section
(`local_dir`, `exclude`, `skip_unchanged`) — see `examples/sync_config.ini`.
Unchanged files are skipped by comparing **size only**: plain FTP has no
modification time that is reliable across servers, so a file edited without
changing its length is not re-uploaded. Set `skip_unchanged = false` when that
matters. Nothing on the remote is ever deleted.

## Development

Run tests:
```bash
tools\run_tests.bat              # unit tests
tools\run_integration_tests.bat  # integration tests (Windows: exercises .bat calls)
```

## License

MIT
