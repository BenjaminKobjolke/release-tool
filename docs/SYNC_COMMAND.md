# `release-tool sync` — upload a directory tree to FTP

Mirrors a local directory to an FTP remote, creating remote directories as
needed. This is the replacement for the `rclone copy <dir> ftp-remote:` calls in
the old bat chains, and the last thing that kept a bundled `rclone.exe` in those
projects.

The other subcommands upload exactly one built artifact; `sync` is for the two
cases that upload a whole tree.

## Usage

```bash
release-tool sync tools\sync_releases.ini --project-root .

# List what would be uploaded, without connecting to the server
release-tool sync tools\sync_releases.ini --project-root . --dry-run
```

| Flag | Meaning |
|---|---|
| `config` | Path to the sync config INI (positional, required) |
| `--project-root` | Root that `local_dir` resolves against (default: cwd) |
| `--dry-run` | List the selected files and exit; connects to nothing |
| `--verbose` | Debug logging, including every excluded and skipped file |

Exit codes follow the rest of the tool: `0` success, `1` failure, `2`
configuration error, `3` FTP error, `130` interrupted.

## Configuration

See [`examples/sync_config.ini`](../examples/sync_config.ini). Two sections:

```ini
[FTP]
host = ftp.example.com
port = 21
username = deploy_user
password = your_password
remote_path = /

[Sync]
local_dir = releases
exclude = windows/**
skip_unchanged = true
```

`[FTP]` is the same section the other subcommands use, with the same validation —
except `remote_filename`, which is rejected here: sync uploads many files and each
keeps its own name.

`[Sync]` keys:

- **`local_dir`** (required) — the directory to upload, relative to
  `--project-root`. Its contents land directly under `remote_path`, so
  `local_dir = releases` with `remote_path = /` puts `releases/linux/app.tar` at
  `/linux/app.tar`.
- **`exclude`** (optional) — comma-separated gitignore-style globs, matched with
  `fnmatch` against each file's path relative to `local_dir` **and** against each
  of its parent directories. So `windows`, `windows/**` and `windows/*` all drop
  the whole folder. Note that `*` crosses `/` in `fnmatch`, so `*.tmp` excludes
  `.tmp` files at every depth.
- **`skip_unchanged`** (optional, default `true`) — skip a file whose remote size
  already matches the local one.

## Why size-only, and what that misses

`rclone copy` defaults to comparing size **and** modification time. Plain FTP has
no modification time that is reliable across servers (`MDTM` is an extension, and
timezone handling differs), so size is the honest equivalent and the only check
this command makes.

The consequence: **a file edited without changing its byte length is not
re-uploaded.** For build artifacts and release archives that never happens. For
hand-edited text — a localization JSON where one word was swapped for another of
the same length — it can. Set `skip_unchanged = false` for those; the tree is
uploaded in full every run.

A remote file the server refuses to `SIZE` counts as changed and is re-uploaded,
so an unhelpful server errs toward doing the work rather than silently skipping.

## Behavior notes

- **Uploads are serial** on one connection. rclone's `--transfers 4` was a
  throughput knob; the calls this replaces already pinned `--transfers=1`.
- **Nothing is deleted.** This is `copy`, not `sync` in rclone's sense — a file
  that exists only on the remote is left alone.
- **Files only.** Empty local directories are not created remotely.
- **Dry run connects to nothing.** It lists the selected files from the local
  walk, so the `skip_unchanged` decisions (which need the server) are not shown.

## Credentials

The bats this replaces held FTP passwords in committed files. Put the INI
somewhere gitignored, and **rotate any password that was ever committed** —
moving the file does not remove it from history.
