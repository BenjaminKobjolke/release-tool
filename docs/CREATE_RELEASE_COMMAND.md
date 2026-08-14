# `release-tool create` — one-command release orchestration

The `create` subcommand runs a project's **whole** release in one command. It
sequences that project's existing batch files, git, and (only when release notes
are missing) a headless Codex call. It does **not** reimplement build or version
logic — it orchestrates the tools the project already has.

This is separate from the base `release-tool` command (FTP publish of a single
file). The publish step of `create` just runs the project's own publish bat,
which typically calls `release-tool` underneath. The legacy invocation
(`release-tool <file> <config> --previous-version ...`) is unchanged.

## Usage

Run from the project root:

```bash
# End-user release: label, notes, build, translate, publish prompt, commit, tag
release-tool create

# Point at a specific config (default: release_create.ini in the cwd)
release-tool create release_create.ini

# Run from elsewhere: config path + explicit project root (see "Launcher bat")
release-tool create path\to\tools\release_create.ini --project-root path\to\project

# Internal test build: skip release notes, tag as INTERNAL
release-tool create --internal

# Preview the resolved label and every command without executing anything
release-tool create --dry-run

# Debug logging
release-tool create --verbose
```

| Argument | Description |
|---|---|
| `config` (positional) | Path to the create config INI. Default: `release_create.ini` in the cwd. |
| `--project-root` | Root the `[Bats]` paths and `notes_dir` resolve against. Default: the cwd. Set it when running from another directory (e.g. the launcher bat cd's into the release-tool repo). |
| `--internal` | Internal test build: skip release notes, commit/tag as `INTERNAL`. |
| `--dry-run` | Print the resolved label and the exact commands without running the mutating ones. |
| `--verbose` | Enable debug logging. |

## What it does

1. **Compute the labels** — the *shipping* label (released now) and the *previous*
   label (the version currently online, used to name its backup). Both derive from
   one `version_get` read (a bare `1.0.0` or a full `1.0.0_21` are both accepted —
   a trailing `_<build>` is stripped), so they can't drift apart. How the shipping
   label is formed depends on **`versioning`** (see "Versioning modes"):
   - `build` (default): `previous = <version>_<build>`, `shipping =
     <version>_<build+1>` — build from `build_get`.
   - `semver`: `previous = <version>`, `shipping = <version>` with its last dotted
     segment +1 (`0.1.6` → `0.1.7`) — `build_get` is not read.

   Computed before anything mutates, so the notes folder targets the shipping label.
   *Bump first, ship next: the counter/version holds the last shipped label.*
2. **Ensure release notes** (skipped with `--internal`). If
   `<notes_dir>/<label>/<en_file>` is missing, author it headlessly via
   `codex exec --dangerously-bypass-approvals-and-sandbox` (authors **only**
   `en.json` — no translate, no build). If the file still doesn't appear, the run
   aborts with a message to author it manually or run `/release:create-release-notes`.
3. **Bump the build** — `build_increment`.
4. **Translate** — `translate` bat (skipped when `english_only = true`).
5. **Build** — `build` bat. **If it fails, `build_decrement` rolls the counter
   back** so the label doesn't drift ahead, then the run aborts.
6. **Record the previous version** — write the previous (online) label to
   `previous_version_file` (default `tools/previous_version.txt`). The publish bat
   reads this for `--previous-version` backup naming, so it never needs
   hand-editing — whether publish runs now (step 7) or by hand later. Gitignore
   this file.
7. **Publish** (optional gate) — if a `publish` bat is configured you are asked
   `Publish <label> to <platform>? [y/N]`. `y` → run the publish bat (no arguments;
   it reads `previous_version_file`). `n`, or no publish bat → skip. **Independent
   of step 8.**
8. **Commit + tag + push** (optional gate) — asked
   `Commit, tag and push <label>? [y/N]`. `y` → `git add -A` (so a fresh
   `release_notes/<label>/` is included), `git commit -m "<TYPE> (<scope>): <label>"`,
   `git tag <label>`, `git push`, `git push origin <label>`. `<TYPE>` is `RELEASE`,
   or `INTERNAL` with `--internal`. **Independent of step 7** — declining publish
   still lets you commit, and vice versa.

## Versioning modes

`versioning` selects how the shipping label is derived and which bats are used:

- **`build`** (default) — version-fixed + build-incrementing. Label =
  `label_format` (default `{version}_{build}`); the build integer comes from
  `build_get` and is bumped by `build_increment` (rolled back by `build_decrement`
  on build failure). Use when the semver version is stable across many builds.
- **`semver`** — no build counter. Each release bumps the **last dotted segment**
  of the version (`0.1.6` → `0.1.7`). `build_get` and `label_format` are ignored;
  `build_increment`/`build_decrement` are the project's version bump/rollback bats
  (e.g. `increment_version.bat` writing `version.txt`). Use for projects whose
  release *is* a patch bump.

## Configuration — `release_create.ini`

Per project the config lives in the project's `tools/` folder alongside a
launcher bat (see "Setup per project"). Set only what differs from the
conventional defaults; everything else falls back. The `[Bats]` paths and
`notes_dir` are always relative to the **project root** (`--project-root`), not
to the config's own folder. See `examples/release_create.ini`.

(When the config sits at the project root and you run `create` from there, the
default cwd is the project root, so no `--project-root` is needed — the legacy
layout still works.)

```ini
; NOTE: configparser does not strip inline `;`/`#` comments — keep active values
; bare; put comments on their own lines.
[Release]
scope = app
publish_platform = Google Play Store

; --- optional overrides (defaults shown) ---
; notes_dir = release_notes
; en_file = en.json
; label_format = {version}_{build}   ; build mode only
; notes_label_format = {version}_{build}  ; notes-folder key; defaults to label_format (see docs/NOTES_LABEL_FORMAT.md)
; versioning = build                 ; build | semver (see "Versioning modes")
; previous_version_file = tools/previous_version.txt  ; where the online version is recorded
; english_only = false               ; true => skip the translate step

[Bats]
; All paths are relative to the project root. Omit a line to keep the default.
; version_get     = tools/version_get.bat
; build_get       = tools/build_get.bat       ; unused in semver mode
; build_increment = tools/build_increment.bat ; version bump bat in semver mode
; build_decrement = tools/build_decrement.bat ; version rollback bat in semver mode
; translate       = tools/translator_app-release-notes.bat
; build           = tools/build_release.bat

; publish has NO default. Set it to offer the publish gate. The bat is called
; with NO arguments — it reads previous_version_file for --previous-version.
; Omitting publish just skips the publish gate; commit/tag/push is still offered.
publish = tools/publish_release.bat
```

### Keys

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[Release]` | `scope` | `app` | Commit scope. |
| `[Release]` | `publish_platform` | *(empty)* | Human name of the publish target, shown in the prompt. |
| `[Release]` | `notes_dir` | `release_notes` | Base folder for release-notes subfolders. |
| `[Release]` | `en_file` | `en.json` | The hand/AI-authored English notes file. |
| `[Release]` | `label_format` | `{version}_{build}` | How the commit/tag label is composed (`build` mode only). |
| `[Release]` | `notes_label_format` | *(= `label_format`)* | Key for the release-notes subfolder, when it must differ from the commit/tag label. See [`docs/NOTES_LABEL_FORMAT.md`](NOTES_LABEL_FORMAT.md). |
| `[Release]` | `versioning` | `build` | `build` (counter) or `semver` (patch bump). See "Versioning modes". |
| `[Release]` | `previous_version_file` | `tools/previous_version.txt` | Where the previous (online) version is recorded for the publish bat. Gitignore it. |
| `[Release]` | `english_only` | `false` | `true` skips the translate step. |
| `[Bats]` | `version_get` | `tools/version_get.bat` | Prints the version. |
| `[Bats]` | `build_get` | `tools/build_get.bat` | Prints the current build integer. |
| `[Bats]` | `build_increment` | `tools/build_increment.bat` | Bumps the build counter. |
| `[Bats]` | `build_decrement` | `tools/build_decrement.bat` | Rolls the build counter back (on build failure). |
| `[Bats]` | `translate` | `tools/translator_app-release-notes.bat` | Generates non-English locales. |
| `[Bats]` | `build` | `tools/build_release.bat` | Builds + bundles the artifact. |
| `[Bats]` | `publish` | *(none)* | Offers the publish gate; the bat reads `previous_version_file`. **Absent/empty → skip publish only** (commit/tag/push still offered). |

## Setup per project

Use the `/release:setup-automated-script` command to wire a project up: it reads
the project's `docs/CREATE_NEW_RELEASE.md`, discovers its `tools/*.bat`, and writes
**two** files into the project's `tools/` folder:

1. `tools/release_create.ini` — the minimal config above.
2. `tools/release_create.bat` — a launcher that runs the full release. It cd's
   into the release-tool repo (so `uv run` resolves this tool's venv — it is not
   on `PATH`), then calls `create` pointed back at the project:

   ```bat
   @echo off
   cd /d D:\GIT\BenjaminKobjolke\release-tool
   call uv run python -m release_tool create "%~dp0release_create.ini" --project-root "%~dp0.." %*
   cd /d "%~dp0"
   ```

   `%~dp0` is the bat's own folder (`…\tools\`), so `"%~dp0release_create.ini"`
   is the config and `"%~dp0.."` is the project root. `%*` forwards
   `--internal` / `--dry-run`. See `examples/release_create.bat`.

It also points the project's publish bat at `previous_version_file` (reads it for
`--previous-version`) and gitignores that file.

Then the one-command release is `tools\release_create.bat` (add `--internal` for
an internal test build), verified with `tools\release_create.bat --dry-run`.

## Requirements

- `git` on `PATH`.
- `codex` on `PATH` (only used when release notes are missing).
- The configured bats present in the target project (verify with `--dry-run`).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | A release step failed (`ReleaseCreateError`). |
| `2` | Configuration error (bad/missing `release_create.ini`). |
| `130` | Cancelled (Ctrl-C). |
