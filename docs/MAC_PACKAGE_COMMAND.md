# `mac-package` — sign and notarize a macOS installer

`mac-package` takes a raw single-file macOS command-line binary and creates a
signed, notarized, stapled `.pkg`. It runs on macOS because `codesign`,
`pkgbuild`, `xcrun`, `pkgutil`, and `spctl` are supplied by Apple's toolchain.
`.app` bundles packaged as `.dmg` or `.zip` are not supported.

```bash
# Build a package using app config plus the shared mac_signing.ini
release-tool mac-package dist/mytool tools/mac_package.ini --project-root .

# Resolve and log all steps without running Apple tools (also works on Windows)
release-tool mac-package dist/mytool tools/mac_package.ini --project-root . --dry-run
```

The binary must exist even in a dry run. Relative paths in the app config and a
relative binary path resolve against `--project-root`, which defaults to the
current directory.

## What it does

1. Signs the raw binary with the Developer ID Application identity, hardened
   runtime options, entitlements, and a secure timestamp.
2. Copies only that binary into a temporary package root and runs `pkgbuild`
   with the configured install location, package identifier, version, optional
   scripts folder, and Developer ID Installer identity.
3. Submits the `.pkg` with `xcrun notarytool submit --wait` and parses its JSON
   result. Only `Accepted` proceeds; an Apple rejection stops before stapling
   and reports the submission id and command for reading Apple's log.
4. Staples Apple's notarization ticket to the package.
5. Verifies the package signature with `pkgutil --check-signature`.
6. Assesses install policy with `spctl --assess --type install`.

The package command does not upload anything. After it succeeds, use the normal
publish command separately, with Mac publishing configured for no Authenticode
pre-signing:

```bash
release-tool releases/mac/mytool.pkg tools/publish_settings_mac.ini
```

```ini
[PreSigning]
enabled = false
```

## Configuration

The app-specific file (see [`examples/mac_package.ini`](../examples/mac_package.ini))
contains `[MacPackage]` values. Shared signing values live in the gitignored
`mac_signing.ini` at the release-tool checkout root (see
[`examples/mac_signing.ini`](../examples/mac_signing.ini)). Each app can also
include `[MacSigning]`; those values override matching shared values. The shared
file is optional if the app file supplies all three signing values.

| Key | Required | Meaning |
|---|---|---|
| `app_identity` | yes | Exact Developer ID Application certificate name |
| `installer_identity` | yes | Exact Developer ID Installer certificate name |
| `keychain_profile` | yes | Profile name saved with `notarytool store-credentials` |
| `identifier` | yes | Unique package identifier, such as `ai.xida.cmdai` |
| `install_location` | yes | Install location passed to `pkgbuild` |
| `scripts` | no | Existing folder passed to `pkgbuild --scripts`; when used, it must contain an executable `postinstall` script |
| `version` or `version_file` | exactly one | Literal package version, or a project-root-relative file whose trimmed contents are the version |
| `output` | yes | Output `.pkg` path; `{version}` is replaced with the resolved version |
| `entitlements` | no | Project-root-relative plist; defaults to the bundled generic PyInstaller entitlements |

`mac_signing.ini` has one `[MacSigning]` section with the three shared keys.
Keep actual certificate identities and profile names out of committed app
configs when they are machine- or team-specific.

## One-time setup on each Mac

1. Install Apple's Xcode Command Line Tools:

   ```bash
   xcode-select --install
   ```

2. In the Apple Developer account, create or download both **Developer ID
   Application** and **Developer ID Installer** certificates. Install them in
   the login keychain and confirm both identities are available to `codesign`
   and `pkgbuild`.
3. Create an app-specific password for the Apple ID used for notarization.
4. Save notarization credentials in the keychain. Choose a profile name and use
   the same value for `keychain_profile`:

   ```bash
   xcrun notarytool store-credentials "<profile>" \
       --apple-id "<apple-id>" \
       --team-id "<team-id>" \
       --password "<app-specific-password>"
   ```

The profile is stored in the user's keychain, so this setup is per Mac and per
user account.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Package created and all verification steps succeeded (or dry run logged) |
| 1 | Signing, package creation, notarization, stapling, verification, or platform failure |
| 2 | Configuration error |
| 130 | Cancelled |
