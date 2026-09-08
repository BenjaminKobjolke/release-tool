# Android projects migrated to `release-tool android`

Which projects moved off their `rclone.exe` bat chains, how each is configured,
and what changed for them. The command itself is documented in
[`ANDROID_COMMAND.md`](ANDROID_COMMAND.md).

## Why

Seven projects under `D:\GIT` each carried a private bat chain doing the same
three things — bump a build number, run the Android build, push the APK to FTP
with a bundled 57 MB `rclone.exe`. The copies had drifted: some bumped, most
didn't; one rewrote `pubspec.yaml` line-by-line and mangled blank lines and
indentation; one reported upload failures as success (`exit /b` with no code);
several uploaded whichever APK `dir /b` happened to list first.

`release-tool` already uploaded over FTP in-process, so `rclone` was redundant.
Two gaps had to be closed: it could not write a version file, and it could not
rename a file on upload (rclone `copyto` semantics). With those filled, one
command replaces every chain.

## Migrated projects

| Project | Stack | `version_file` | `version_file_format` | Remote name |
|---|---|---|---|---|
| `android\tickets-app` | Flutter | `pubspec.yaml` | `pubspec` | `tickets.apk` |
| `android\turbo-habits-app` | Flutter | `pubspec.yaml` | `pubspec` | `turbo-habits.apk` |
| `android\android_folder_gallery` | Flutter | `pubspec.yaml` | `pubspec` | `folder-gallery.apk` |
| `block-screen-app` | Flutter | `pubspec.yaml` | `pubspec` | `block-screen.apk` |
| `android\bkmedialibrary` | Gradle (Kotlin DSL) | `app/build.gradle.kts` | `gradle_kts` | `bkmedialibrary.apk` |
| `FastTrack` | Gradle (version catalog) | `gradle/libs.versions.toml` | `toml` | `fasttrack.apk` |
| `monocles_chat` | Gradle (Groovy) | `build.gradle` | `gradle_groovy` | `monocles-chat.apk` |

Each has a gitignored `tools/android_release.ini` and a committed
`tools/android_release_example.ini`.

### Per-project notes

**tickets-app** — the reference case: pure Flutter defaults, no `[Build]`
section at all.

**turbo-habits-app** — `[Build] command` points at `build_android.bat`, which
refreshes the bundled release-notes assets into `pubspec.yaml` before building;
dropping that step would have shipped APKs without their release notes.
`bump_on_debug = true` preserves its debug-bumping behavior.
`build_number_increment.bat` survives as a `bump-build` shim because
`build_release.bat` calls it.

**android_folder_gallery** — like turbo, plus its release APK is at
`build/app/outputs/apk/release/`, **not** the `flutter-apk` default, so
`[Build] apk` is set. Both `build_number_increment.bat` and
`build_number_decrement.bat` survive as shims: `release_create.ini` wires them as
`build_increment` / `build_decrement`.

**block-screen-app** — no `[Build]` section; the tool's defaults match exactly.
Its `build_android.bat` is untouched because `github-release.bat` calls it, and
`config.bat` keeps `LOCAL_DIR`/`FILENAME` for that, plus the demo-recording keys
(`AUTOMATION_HOST`, `DEMO_EMULATOR`, …).

**bkmedialibrary / FastTrack** — native Gradle. `build_android.bat` stays as the
build step: it already resolves the Gradle task and output dir, and
bkmedialibrary sets `GRADLE_USER_HOME` to keep the Gradle cache on the project's
drive. FastTrack's `versionCode` lives in the version catalog, not in
`build.gradle.kts`, which only reads it via `libs.versions.versionCode`.

**monocles_chat** — debug-only; its launcher is `build_and_upload_debug.bat` and
always passes `--debug`, so `bump_on_debug = true` is what makes it bump at all.
`versionCode` is declared **twice** (`defaultConfig` and a product flavor); the
tool rewrites both together and refuses to bump if they ever disagree. The build
emits one APK per ABI and the old uploader took whichever sorted first — the
arm64-v8a one — which is now named explicitly in the config.

## Behavior changes

- **bkmedialibrary, FastTrack, block-screen-app and monocles_chat now bump a
  version number on every build.** Their old chains never did.
- **Debug builds do not bump by default.** turbo-habits and
  android_folder_gallery set `bump_on_debug = true` to keep the behavior they
  had; the others do not.
- **Only the target APK is deleted before a build**, not the whole output
  directory — the old wipe destroyed the other variant's APK each time.
- **monocles_chat's uploaded APK is now pinned to arm64-v8a** instead of
  depending on directory listing order.
- **Upload failures now fail.** turbo-habits' uploader exited without a code, so
  `if errorlevel 1` never fired and a failed upload was reported as success.
- **`pubspec.yaml` rewrites are non-destructive.** turbo-habits and
  android_folder_gallery bumped with a batch `for /f` loop that rebuilt the whole
  file, dropping blank lines and leading whitespace. The splice now preserves the
  file byte-for-byte apart from the number, CRLF included.

## Not migrated

**`Intern\ai-chat`** — does not fit the command's model, and keeps its
`rclone.exe`:

- its uploads keep the original APK filename rather than renaming to a fixed one,
  so the download URL changes per version — the opposite of what
  `remote_filename` does, and that key is required;
- each upload also ships a companion `ftp_htaccess` file;
- there are three artifacts (release APK, debug APK, and a *universal* APK from
  the bundle output), against the command's two variants.

**`Intern\ai-cmd`** — `tools\sync_releases.bat` mirrors a whole `releases/`
directory tree with excludes, which is a different feature. See
[`../PLAN_DIRECTORY_SYNC.md`](../PLAN_DIRECTORY_SYNC.md), which also covers
ai-chat's localization-folder upload.

## Credentials

FTP passwords moved out of `tools/config.bat` into gitignored
`tools/android_release.ini` files. Two caveats:

- turbo-habits' `config.bat` was **tracked**, so its old password is still in git
  history; moving the file does not remove it. That account's password has since
  been rotated. The other projects' `config.bat` files were untracked.
- **Still exposed:** `ai-chat/tools/upload_release-apk-to-ftp.bat` (tracked) and
  `ai-cmd/tools/sync_releases.bat` hold plaintext credentials for a *different*
  account, on `w01dfd34.kasserver.com` and `w01de2f0.kasserver.com`. Rotating
  those is outstanding.

## Verifying a migration

```bat
tools\build_and_upload_android.bat --dry-run --verbose
tools\build_and_upload_android.bat debug --dry-run
```

A dry run resolves the build command, APK path, remote name and public URL, and
writes nothing: the version file must be byte-identical afterwards. Then check
the bump round-trips:

```bat
release-tool bump-build <version file> --format <format>
release-tool bump-build <version file> --format <format> --decrement
```

For a project wired into `release-tool create`, also confirm
`tools\release_create.bat --dry-run` still resolves through the shimmed
increment/decrement bats.
