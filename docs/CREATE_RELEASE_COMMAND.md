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
| `--internal` | Internal test build: skip release notes, commit/tag as `INTERNAL`. |
| `--dry-run` | Print the resolved label and the exact commands without running the mutating ones. |
| `--verbose` | Enable debug logging. |

## What it does

1. **Compute the next label** — `<version>_<build+1>`. The version comes from the
   `version_get` bat (a bare `1.0.0` or a full `1.0.0_21` are both accepted — a
   trailing `_<build>` is stripped); the build comes from `build_get`. Computed
   before anything mutates, so the notes folder targets the shipping label.
   *Build first, ship next: the counter holds the last shipped build.*
2. **Ensure release notes** (skipped with `--internal`). If
   `<notes_dir>/<label>/<en_file>` is missing, author it headlessly via
   `codex exec --dangerously-bypass-approvals-and-sandbox` (authors **only**
   `en.json` — no translate, no build). If the file still doesn't appear, the run
   aborts with a message to author it manually or run `/release:create-release-notes`.
3. **Bump the build** — `build_increment`.
4. **Translate** — `translate` bat (skipped when `english_only = true`).
5. **Build** — `build` bat. **If it fails, `build_decrement` rolls the counter
   back** so the label doesn't drift ahead, then the run aborts.
6. **Publish** — the single interactive gate. If a `publish` bat is configured you
   are asked once: `Publish <label> to <platform>? [y/N]`.
   - `y` → run the publish bat, then step 7.
   - `n`, or no publish bat configured → report the built artifact, **skip step 7**
     (no commit, no tag — nothing was shipped).
7. **Commit + tag** — `git add -A` (so a fresh `release_notes/<label>/` is
   included), then `git commit -m "<TYPE> (<scope>): <label>"` and `git tag <label>`.
   `<TYPE>` is `RELEASE` for an end-user release, `INTERNAL` with `--internal`.
   Only `RELEASE` should advance the anchor release-notes diff against.

## Configuration — `release_create.ini`

Placed at the project root (the default path `create` reads). Set only what
differs from the conventional defaults; everything else falls back. See
`examples/release_create.ini`.

```ini
[Release]
scope = app                          ; commit scope in "RELEASE (<scope>): <label>"
publish_platform = Google Play Store ; named in the publish prompt

; --- optional overrides (defaults shown) ---
; notes_dir = release_notes
; en_file = en.json
; label_format = {version}_{build}
; english_only = false               ; true => skip the translate step

[Bats]
; All paths are relative to the project root. Omit a line to keep the default.
; version_get     = tools/version_get.bat
; build_get       = tools/build_get.bat
; build_increment = tools/build_increment.bat
; build_decrement = tools/build_decrement.bat
; translate       = tools/translator_app-release-notes.bat
; build           = tools/build_release.bat

; publish has NO default. Set it to enable publish + commit + tag.
; Leave it out (or empty) to build and stop.
publish = tools/publish_release.bat
```

### Keys

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[Release]` | `scope` | `app` | Commit scope. |
| `[Release]` | `publish_platform` | *(empty)* | Human name of the publish target, shown in the prompt. |
| `[Release]` | `notes_dir` | `release_notes` | Base folder for release-notes subfolders. |
| `[Release]` | `en_file` | `en.json` | The hand/AI-authored English notes file. |
| `[Release]` | `label_format` | `{version}_{build}` | How the label is composed. |
| `[Release]` | `english_only` | `false` | `true` skips the translate step. |
| `[Bats]` | `version_get` | `tools/version_get.bat` | Prints the version. |
| `[Bats]` | `build_get` | `tools/build_get.bat` | Prints the current build integer. |
| `[Bats]` | `build_increment` | `tools/build_increment.bat` | Bumps the build counter. |
| `[Bats]` | `build_decrement` | `tools/build_decrement.bat` | Rolls the build counter back (on build failure). |
| `[Bats]` | `translate` | `tools/translator_app-release-notes.bat` | Generates non-English locales. |
| `[Bats]` | `build` | `tools/build_release.bat` | Builds + bundles the artifact. |
| `[Bats]` | `publish` | *(none)* | Publishes. **Absent/empty → build-and-stop.** |

## Setup per project

Use the `/release:setup-automated-script` command to generate a project's
`release_create.ini`: it reads the project's `docs/CREATE_NEW_RELEASE.md`, discovers
its `tools/*.bat`, writes a minimal config, and verifies it with a `--dry-run`.

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
