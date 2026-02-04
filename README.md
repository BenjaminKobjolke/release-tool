# Release Tool

CLI tool for releasing software via FTP.

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

## Development

Run tests:
```bash
tools\tests.bat
```

## License

MIT
