# `mac-sign` — sign and notarize an app or disk image

`mac-sign` signs one existing macOS `.app` bundle or `.dmg` image in place,
submits it to Apple for notarization, staples Apple's ticket, and verifies the
result. It runs on macOS with the Xcode Command Line Tools installed. Use
`--dry-run` to log the commands without running Apple tools; dry runs also work
on Windows.

```bash
# Sign an app bundle with its app-specific hardened-runtime entitlements
release-tool mac-sign target/fman.app --entitlements src/sign/mac/entitlements.plist

# Sign the disk image built from the stapled app
release-tool mac-sign target/fman.dmg

# Preview the commands without changing the target
release-tool mac-sign target/fman.app --dry-run
```

The target must exist, including during a dry run. Kind is selected from the
suffix: `.app` must be a directory and `.dmg` must be a file. Relative target
and entitlements paths resolve from the current working directory.

## What it does

For an `.app` bundle, the command:

1. Signs the app with `codesign --deep --force --options=runtime`, a secure
   timestamp, and the selected entitlements plist.
2. Creates a temporary zip with `ditto`, preserving resource forks and the
   parent directory.
3. Submits that zip to `notarytool` and requires an `Accepted` result. The
   temporary zip is removed even if notarization fails.
4. Staples Apple's ticket to the `.app`, validates the staple, and assesses the
   app with Gatekeeper.

For a `.dmg` image, the command signs the image without app entitlements,
submits the image itself for notarization, staples and validates its ticket,
then assesses the image with Gatekeeper. If `--entitlements` is supplied for a
`.dmg`, it is ignored and a message is logged.

For an `.app`, `--entitlements <plist>` selects its hardened-runtime entitlements.
When omitted, the bundled `mac_entitlements.plist` is used. A selected app
entitlements file must exist.

## Configuration

The command reads only `app_identity` and `keychain_profile` from the shared
`mac_signing.ini` `[MacSigning]` section at the release-tool checkout root. It
does not need an app-specific INI or a Developer ID Installer certificate.

```ini
[MacSigning]
app_identity = Developer ID Application: Your Name (TEAMID)
keychain_profile = your-profile
```

See [`examples/mac_signing.ini`](../examples/mac_signing.ini) for the shared
configuration example. The one-time Xcode and keychain setup is documented in
[`MAC_PACKAGE_COMMAND.md`](MAC_PACKAGE_COMMAND.md#one-time-setup-on-each-mac).
The Developer ID Installer certificate in that setup is needed only for
`mac-package`.

## `mac-sign` vs. `mac-package`

- `mac-package` takes a raw single-file CLI binary and builds a signed,
  notarized installer `.pkg`.
- `mac-sign` takes an `.app` bundle or `.dmg` image that a build tool such as
  fbs has already produced, and signs that artifact in place.

A typical app release signs the `.app`, builds a `.dmg` from that stapled app,
then signs the `.dmg`:

```bash
release-tool mac-sign target/fman.app --entitlements src/sign/mac/entitlements.plist
# Build target/fman.dmg from the stapled app.
release-tool mac-sign target/fman.dmg
```

## Notarization failures and exit codes

When Apple rejects a submission, the command fetches and prints the issues from
`notarytool log <id>` when Apple provides a submission id. It exits before
stapling the target. A failure to fetch the log is reported as a warning while
the rejection remains an error.

| Code | Meaning |
|---|---|
| 0 | Signing, notarization, stapling, and verification succeeded (or dry run logged) |
| 1 | Signing, notarization, stapling, verification, target, or platform failure |
| 2 | Shared signing configuration error |
| 130 | Cancelled |
