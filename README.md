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
release-tool myapp.zip config.ini --version 1.9.5

# Preview without changes
release-tool dist/app.exe release.ini --dry-run

# Verbose output (debug logging)
release-tool myapp.exe config.ini --verbose
```

## Options

| Option | Description |
|--------|-------------|
| `--version`, `-v` | Version string for backup naming (used with `subfolder_naming = version`) |
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
; Naming: "timestamp" (YYYYMMDD_HHMMSS) or "version" (uses --version arg)
subfolder_naming = timestamp
```

## Development

Run tests:
```bash
tools\tests.bat
```

## License

MIT
