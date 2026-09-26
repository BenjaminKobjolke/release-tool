# `android` — build an APK and upload it

Replaces the per-project bat chain that bumps the build number, runs
`fvm flutter build apk`, and pushes the APK to FTP with a bundled `rclone.exe`.

```bash
# Release build: bump, build, verify, upload as <remote_filename>
release-tool android tools/android_release.ini --project-root .

# Debug build: no bump, uploads as <name>-debug.apk
release-tool android tools/android_release.ini --project-root . --debug

# Preview everything without changing a file or touching the server
release-tool android tools/android_release.ini --project-root . --dry-run --verbose
```

| Argument | Meaning |
|---|---|
| `config` | Path to the android config INI (see `examples/android_release.ini`) |
| `--project-root` | Root the build command and all `[Build]` paths resolve against (default: cwd) |
| `--debug` | Build the debug variant instead of the release one |
| `--dry-run` | Log every resolved step; write nothing, upload nothing |
| `--verbose` | Debug logging |

## What it does

1. **Resolve the variant.** Release or debug decides the build command, the APK
   path, the remote filename and whether to bump — all derived from that one flag.
2. **Bump the build number** in `pubspec.yaml` (`version: 1.0.0+2` → `+3`). Release
   builds only, unless `bump_on_debug = true`. The semver name is never touched;
   edit it by hand.
3. **Delete the target APK** so the verification below cannot pass on a stale one.
4. **Run the build command** with the working directory set to `--project-root`.
5. **Verify the APK exists.** A build that exits 0 without producing the APK fails
   here, and the bump is rolled back.
6. **Upload** through the normal publish path, renaming the file to
   `[FTP] remote_filename` (this is what `rclone copyto` used to do).
7. **Upload the version sidecar** as `<remote_filename>.json`, after the APK is
   online. The app downloads webpage reads `version` and `version_code` from it.
   Gradle versions without a name contain only `version_code`; debug builds use
   names such as `myapp-debug.apk.json`.
8. **Report** the version, the APK's last-modified time and the public URL.

If the build fails, the build-number bump is rolled back with a decrement. A
rollback that itself fails is logged but never hides the original build error.

## Configuration

`[FTP]` and `[OldFileHandling]` are the same sections the base publish command
uses (see `PUBLISH_COMMAND.md`), with two additions:

Shared credentials and paths may be selected with `profile`; see
[`FTP_PROFILES.md`](FTP_PROFILES.md). Project keys override profile keys.

| Key | Section | Default | Meaning |
|---|---|---|---|
| `remote_filename` | `[FTP]` | — (**required**) | Name the APK gets on the server. Bare filename; a path is rejected |
| `public_url_base` | `[FTP]` | none | Base of the public URL, reported after upload |

`[PreSigning]` is rejected: Authenticode signing does not apply to an APK, and
the signer wait would block until it timed out.

`[Build]` is optional — the defaults fit a standard Flutter project:

| Key | Default |
|---|---|
| `command` | `fvm flutter build apk --release` |
| `command_debug` | `fvm flutter build apk --debug` |
| `apk` | `build/app/outputs/flutter-apk/app-release.apk` |
| `apk_debug` | `build/app/outputs/flutter-apk/app-debug.apk` |
| `version_file` | `pubspec.yaml` |
| `version_file_format` | `pubspec` |
| `bump_on_debug` | `false` |

### Version file formats

Every release build bumps a build number, so non-Flutter projects set
`version_file` and `version_file_format` to point at their own version line:

| `version_file_format` | Line it rewrites | Typical `version_file` |
|---|---|---|
| `pubspec` (default) | `version: 1.0.0+490` | `pubspec.yaml` |
| `gradle_kts` | `versionCode = 1` | `app/build.gradle.kts` |
| `gradle_groovy` | `versionCode 201` | `app/build.gradle` |
| `toml` | `versionCode = "38"` | `gradle/libs.versions.toml` |

Only the build number is written; a version name (`versionName`, or pubspec's
`1.0.0`) is edited by hand. The Gradle formats carry no name, so the reported
label is the build number alone.

If a file declares the build number more than once — Gradle projects often set
`versionCode` in both `defaultConfig` and a product flavor — every occurrence is
rewritten together. Occurrences that disagree are an error naming the lines,
rather than a guess about which one wins.

Adding a fifth format means adding a pattern and a render function to
`VERSION_FORMATS` in `src/release_tool/version_file.py` — no subclass, no factory.

### A Gradle project

```ini
[Build]
; Keep the project's own build bat as the build step: it already resolves the
; Gradle task and output dir, and may set GRADLE_USER_HOME for a real reason.
command = cmd /c call tools\build_android.bat release
command_debug = cmd /c call tools\build_android.bat debug
apk = app/build/outputs/apk/release/app-release.apk
apk_debug = app/build/outputs/apk/debug/app-debug.apk
version_file = app/build.gradle
version_file_format = gradle_groovy
```

Commands are argv parsed with `shlex`, so quoted arguments survive.

## `bump-build`

The build-number bump on its own, for projects that build through another script:

```bash
release-tool bump-build ../pubspec.yaml              # 1.0.0+2 -> 1.0.0+3
release-tool bump-build ../pubspec.yaml --decrement  # 1.0.0+3 -> 1.0.0+2

# Non-Flutter projects pass their format
release-tool bump-build ../app/build.gradle --format gradle_groovy
```

The rewrite is an in-place splice of the `version:` line, so line endings, blank
lines and indentation elsewhere in the file are preserved byte-for-byte. The
build number will not go below 1.

## Migrating a project off the bats

See [`ANDROID_MIGRATION.md`](ANDROID_MIGRATION.md) for the projects already
migrated, their exact configs, and the behavior changes that came with each.

| Old file | Becomes |
|---|---|
| `build_and_upload_android.bat` | A launcher (see below) |
| `upload_*_to_ftp.bat` | Deleted — the upload is in-process |
| `rclone.exe` | Deleted. It is untracked in these repos, so this is **not** git-recoverable — re-download from rclone.org if something still needs it |
| `build_number_increment.bat` | Deleted, **or** kept as a shim calling `release-tool bump-build` when another script calls it (`build_release.bat`, or `create`'s `build_increment`) |
| `build_number_decrement.bat` | Deleted — rollback is built in. Keep it as a `--decrement` shim if `release_create.ini` wires it as `build_decrement` |
| `build_android.bat` | Kept as the `[Build] command` when it does more than call the compiler (release-notes assets, `GRADLE_USER_HOME`, a Gradle task) — minus its bump and upload |
| `config.bat` (FTP/APK keys) | `android_release.ini`, gitignored |

Commit an `android_release_example.ini` next to the real one, and add the real
one to `.gitignore` — it holds the FTP password.

The launcher is not a one-liner, because two batch gotchas bite:

```bat
@echo off
setlocal
REM `shift` below also shifts %0, so %~dp0 must be captured first.
set "TOOLS_DIR=%~dp0"

REM Translate the historical `debug`/`release` positional into the tool's flags.
REM Built in a loop because %* ignores shift.
set "ARGS="
:parse_args
if "%~1"=="" goto run
if /i "%~1"=="debug" (
    set "ARGS=%ARGS% --debug"
) else if /i "%~1"=="release" (
    rem release is the default; nothing to pass
) else (
    set "ARGS=%ARGS% %~1"
)
shift
goto parse_args

:run
REM release-tool is not on PATH; cd into its repo so `uv run` finds the venv.
cd /d D:\GIT\BenjaminKobjolke\release-tool
call uv run python -m release_tool android "%TOOLS_DIR%android_release.ini" --project-root "%TOOLS_DIR%.."%ARGS%
set "EXIT_CODE=%ERRORLEVEL%"
cd /d "%TOOLS_DIR%"
endlocal & exit /b %EXIT_CODE%
```

Three deliberate differences from the bats:

- **Every release build bumps.** Several projects never bumped a version number
  at all; they do now. `bump_on_debug = true` additionally bumps debug builds,
  for projects whose old chain did that.
- **Only the target APK is deleted** before a build, not the whole output
  directory. Both variants land in the same folder, so the old wipe destroyed the
  other variant's APK on every build.
- **The APK to upload is named explicitly.** Several uploaders took whichever
  `dir /b` listed first, which silently picked one of several ABI splits.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Build failed, APK missing, or upload reported failure |
| 2 | Configuration error (missing INI, missing `remote_filename`, bad value) |
| 3 | FTP error |
| 130 | Cancelled |
