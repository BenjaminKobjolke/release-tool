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
2. **Ensure release notes** (skipped with `--internal`) — if `en.json` is missing
   for the shipping label, author it headlessly via
   `codex exec --dangerously-bypass-approvals-and-sandbox`; abort if it still
   doesn't appear.
3. **Bump the build**, then **translate** (unless `english_only`), then **build**.
   If build fails, the build counter is rolled back automatically.
4. **Publish** — the single interactive gate. If a publish bat is configured you
   are asked once (`Publish <label> to <platform>? [y/N]`). Decline, or configure
   no publish bat, and it stops after the build (no commit, no tag).
5. **Commit + tag** — `RELEASE (<scope>): <label>` (or `INTERNAL (...)`).

### `release_create.ini`

Only per-project differences need to be set; everything else uses conventional
defaults (see `examples/release_create.ini`):

```ini
[Release]
scope = app                          ; commit scope
publish_platform = Google Play Store ; named in the publish prompt
; notes_dir = release_notes          ; optional overrides shown with defaults
; en_file = en.json
; label_format = {version}_{build}
; english_only = false

[Bats]
; All paths relative to the project root; omit a line to keep the default.
; version_get / build_get / build_increment / build_decrement / translate / build
; publish has NO default — set it to enable publish + commit + tag, omit to build-and-stop.
publish = tools/publish_release.bat
```

The legacy publish invocation (`release-tool <file> <config> ...`) is unchanged
and continues to work exactly as before.

## Development

Run tests:
```bash
tools\run_tests.bat              # unit tests
tools\run_integration_tests.bat  # integration tests (Windows: exercises .bat calls)
```

## License

MIT
