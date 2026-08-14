# `notes_label_format` — decoupling the notes folder from the commit/tag label

`release-tool create` derives one release **label** from a single version/build
read and uses it for two different things:

1. the **commit message and git tag** (`RELEASE (<scope>): <label>`, `git tag <label>`), and
2. the **release-notes subfolder** it looks up / authors (`<notes_dir>/<label>/<en_file>`).

`label_format` (default `{version}_{build}`) shapes both. That is fine when the
folder name and the tag are meant to match. Some projects need them to differ —
that is what **`notes_label_format`** is for.

## When you need it

The notes folder and the tag diverge whenever another tool already fixes the
folder name. The motivating case is **Flutter + Google Play**:

- The Play upload selects release notes by **build number**
  (`--release-notes-use-buildnumber`), so notes must live at
  `assets/release-notes/<build>/` — the folder name is the bare build integer.
- But the project's tag/commit convention is `version+build`
  (e.g. `RELEASE (android): 1.1.0+1268`).

One `label_format` cannot be both `1268` and `1.1.0+1268`. Set:

```ini
[Release]
label_format       = {version}+{build}
notes_label_format = {build}
```

Result for build 1267 → 1268:

| Consumer            | Format               | Value        |
|---------------------|----------------------|--------------|
| commit / git tag    | `label_format`       | `1.1.0+1268` |
| release-notes folder| `notes_label_format` | `1268`       |

`create` then looks up (and, if missing, authors via Codex) release notes at
`assets/release-notes/1268/en.json`, while committing and tagging `1.1.0+1268`.

## Default and placeholders

- **Default:** absent, `notes_label_format` mirrors `label_format` — existing
  configs behave exactly as before.
- **Placeholders:** same as `label_format` — `{version}` (from `version_get`,
  trailing `_<build>` stripped) and `{build}` (from `build_get`, the *next* build).
- **`versioning = semver`:** there is no build counter, so the notes label always
  equals the shipping version; `notes_label_format` has no effect in semver mode.

All three derived labels (`previous`, `shipping`, `notes`) come from the same
version/build read, so they cannot drift apart.

## See also

- `docs/CREATE_RELEASE_COMMAND.md` — the full `create` command and config reference.
- `examples/release_create.ini` — commented template.
