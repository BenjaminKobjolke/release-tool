# `release-tool github-release` — create a GitHub Release for a tag

Creates (or, on re-run, updates) a GitHub Release for an existing tag and attaches
one or more asset files — typically the signed installer/executable a project just
built. Shells out to the **`gh` CLI**, so the package stays free of runtime
dependencies (`requests`/`PyGithub`) and `gh` owns authentication.

Standalone command — call it by hand or from a project's own release bat (see
`sign_exe.bat`-style wrappers). It is also available as an optional gate inside the
[`create`](CREATE_RELEASE_COMMAND.md) workflow via the `[GitHubRelease]` INI section.

## Prerequisites

- [`gh` CLI](https://cli.github.com/) installed and on `PATH`.
- Authenticated once: `gh auth login` (scope: `repo`).

## Usage

```bash
release-tool github-release <tag> [assets...]
    [--repo OWNER/NAME] [--title T]
    [--notes TEXT | --notes-file F | --notes-json EN_JSON]
    [--dry-run] [--verbose]
```

| Argument | Description |
|---|---|
| `tag` (positional) | The git tag the release attaches to (e.g. `v1.7.5`). Must already exist and be pushed. |
| `assets` (positional, 0+) | Files to attach to the release. |
| `--repo` | `OWNER/NAME`. `gh` otherwise infers the repo from the git remote of the working directory — pass this whenever the command doesn't run from inside the target repo's checkout. |
| `--title` | Release title. Defaults to `tag`. |
| `--notes` | Release notes as literal text. |
| `--notes-file` | Path to a markdown file with the release notes. |
| `--notes-json` | An XIDA release-notes `en.json` (`{"title": ..., "notes": [...]}`), rendered to markdown. |
| `--dry-run` | Log the `gh` command that would run, without running it. |
| `--verbose` | Debug logging. |

None of `--notes`/`--notes-file`/`--notes-json` given → `gh --generate-notes`
(auto-generated from commits).

## What it does

1. Verify `gh` is on `PATH` and every asset file exists.
2. Run `gh release create <tag> <assets...> --title <title> [--notes-file <f> |
   --generate-notes] [--repo <repo>]`.
3. **Idempotent re-run:** if `gh` reports the release already exists, fall back to
   `gh release upload <tag> <assets...> --clobber` — re-uploading the assets over
   the existing release. Notes/title are not rewritten on re-run.

## Example

```bash
release-tool github-release v1.7.5 target\fmanSetup.exe \
    --repo BenjaminKobjolke/fman \
    --notes-json release_notes\1.7.5_3\en.json \
    --title "fman 1.7.5"
```

## Using it from the `create` workflow

Add a `[GitHubRelease]` section to `release_create.ini` (see
`examples/release_create.ini`):

```ini
[GitHubRelease]
enabled = true
assets = target/fmanSetup.exe   ; comma-separated, relative to the project root
; repo = OWNER/NAME             ; only needed if the checkout's remote can't resolve it
; tag_format   = {label}        ; e.g. v{label} for a "v" prefix
; title_format = {label}
```

`create` then offers a `Create GitHub Release <tag>? [y/N]` gate right after the
commit/tag/push gate — and only if that one actually ran (a release can't attach to
an unpushed tag). Notes are rendered from the shipping release's `en.json`
(skipped for `--internal` builds).

## Exit codes

Mapped in `cli._guarded`: `0` success, `1` a release step failed
(`GitHubReleaseError`/other `ReleaseToolError`), `130` cancelled (Ctrl-C).
