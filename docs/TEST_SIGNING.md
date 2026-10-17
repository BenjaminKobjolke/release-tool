# Test signing

Check a signing setup without building or uploading a release. The test signs a
copy of `examples\dummy.exe`, a tiny unsigned program kept in the repository for
this purpose.

## Prerequisites

1. `signing_profiles.ini` in the release-tool checkout root, with at least one
   profile. Start from `examples/signing_profiles.ini`; see
   [Named signing profiles](FTP_PROFILES.md#named-signing-profiles).
2. For `method = remote`: a SafeNet signer checkout at the profile's
   `signer_dir`, with `config.json` set to `"mode": "client"` and its `client`
   block filled in (host, port, username, password, `server_cert_sha256`).
   The signing server must be running.
3. For `method = network`: the signing service watching `network_path`, and
   both network paths reachable from this PC.

## Run the test

```bat
tools\test_signing.bat "xida remote"
```

Replace `xida remote` with your profile's section name. The script:

1. Copies `examples\dummy.exe` to `%TEMP%\release-tool-signing-test.exe`, so the
   committed file stays unsigned.
2. Runs `release-tool sign <copy> <profile>`, which sends the copy through the
   profile's signing method and replaces it with the signed result.
3. Verifies that the signed file's certificate name matches the profile's
   `expected_signer`.

Options are passed through:

- `--verbose` — debug logging.
- `--profiles <path>` — use another signing profiles file.

To sign a different file the same way, call the command directly:

```bat
start.bat sign "C:\path\to\file.exe" "xida remote"
```

The file is signed in place.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Signing worked and the signer name matches |
| `1` | Signing failed: signer error, timeout, or signer name mismatch |
| `2` | Configuration error: missing file, unknown or disabled profile, missing profile keys |

With `method = remote`, the console also shows the signer's progress and the
meaning of its exit code (wrong client mode, server-side signing failure,
timeout, or connection problem).

## Troubleshooting

- **Profile not found** — the error lists the available profile names; check
  the section name and quoting.
- **Remote signer not found** — `signer_dir` does not contain `sign.bat`.
- **Connection or transfer error** — check the signer's `client` host and port,
  the server's port forwarding, and that the signing server is running.
- **Fingerprint does not match configured pin** — the server certificate changed;
  copy the new SHA-256 fingerprint from the server's log into
  `server_cert_sha256`.
- **Signature mismatch** — the file was signed by a different certificate than
  `expected_signer`; fix the profile's `expected_signer` or the server's
  certificate.
