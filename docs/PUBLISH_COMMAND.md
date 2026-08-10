# `release-tool` — base publish command (FTP upload of one file)

The base command uploads a **single built artifact** to an FTP server, handling
the file already there (delete it, or move it to a versioned/timestamped backup),
and optionally pre-signs the file and uploads a `release_notes/` tree alongside it.

This is the low-level step. The [`create`](CREATE_RELEASE_COMMAND.md) subcommand
orchestrates a whole release and calls a project's *publish bat*, which in turn
runs this command. You rarely call it by hand.

## Usage

```bash
release-tool <file> <config> [--previous-version X] [--dry-run] [--verbose]
```

| Argument | Description |
|---|---|
| `file` (positional) | Path to the artifact to upload (e.g. `dist\App.exe`). |
| `config` (positional) | Path to the release INI (FTP + handling; see below). |
| `--previous-version`, `-p` | Version string used to name the **backup folder** of the file being replaced, when `subfolder_naming = version`. See "Backup naming". |
| `--dry-run` | Print every action (connect, backup, upload) without changing anything remote. |
| `--verbose` | Debug logging. |

## What it does

1. Verify the local `file` exists (else fail).
2. If `--previous-version` is set and the policy is `rename`, check whether that
   backup folder already exists remotely and prompt before overwriting.
3. **Pre-sign** (optional) — copy the file to a network signing folder, wait for
   the signed copy, verify the signer, move it back. See `RETRIEVE_EXECUTABLE_SIGNER.md`.
4. Connect via FTP. If a file with the same name already exists remotely, apply the
   **old-file policy** (delete, or move to a backup subfolder).
5. Upload the artifact.
6. **Release notes** (optional) — upload the configured local notes folder to its
   remote path.

## Backup naming — where `--previous-version` matters

When `[OldFileHandling] policy = rename`, the file currently online is moved into
`<subfolder_base>/<suffix>/` before the new one is uploaded. The `suffix` is:

- `subfolder_naming = version` → the `--previous-version` value (e.g. `0.1.6`).
  **If `--previous-version` is empty/missing, it falls back to a timestamp** with a
  warning — so a missing value is safe, just less tidy.
- `subfolder_naming = timestamp` → always a `YYYYMMDD_HHMMSS` stamp;
  `--previous-version` is ignored.

`--previous-version` is the version *being replaced* (the one currently online),
not the new one. In a `create`-driven release this is supplied **automatically**:
`create` records the pre-increment version to `previous_version_file`
(default `tools/previous_version.txt`, gitignored), and the project's publish bat
reads it. The bat should resolve it as: use `%1` if given, else read the file —

```bat
set "PREV=%~1"
if not defined PREV if exist "%~dp0previous_version.txt" set /p "PREV="<"%~dp0previous_version.txt"
call uv run python -m release_tool "%EXE%" "%CONFIG%" --previous-version "%PREV%" --verbose
```

An empty value (no arg, no file) falls back to timestamp naming — safe.

## Configuration INI

Parsed by `ReleaseConfig.from_ini_file` (`src/release_tool/config.py`).

```ini
[FTP]
host = ftp.example.com
port = 21                 ; default 21
username = user
password = secret
remote_path = /public     ; default /

[OldFileHandling]
policy = rename           ; delete | rename   (default delete)
subfolder_base = versions ; default old_versions
subfolder_naming = version ; version | timestamp  (default timestamp)

[PreSigning]              ; optional; whole section may be omitted
enabled = false
network_path = \\signer\in
network_path_signed = \\signer\out
expected_signer = Example GmbH
poll_interval = 10        ; seconds (default 10)
timeout = 300             ; seconds (default 300)

[ReleaseNotes]           ; optional; both keys required if present
path = release_notes             ; local folder
remote_path = /public/release_notes
```

Keep credentials out of source control — the project keeps this INI gitignored
(commit a `*_example.ini` template instead).

## Exit codes

Mapped in `cli._guarded`:

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | A release step failed (generic `ReleaseToolError`, or upload returned false). |
| `2` | Configuration error (bad/missing INI, missing required FTP fields). |
| `3` | FTP error (connect/transfer). |
| `130` | Cancelled (Ctrl-C). |
