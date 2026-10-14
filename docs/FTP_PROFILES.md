# Named FTP profiles

Store shared FTP settings in `ftp_profiles.ini` at the release-tool checkout
root. The file is gitignored because it may contain credentials. Start from
`examples/ftp_profiles.ini`:

```ini
[kobjolke.com - apps]
host = ftp.example.com
port = 21
username = deploy_user
password = your_password
remote_path = /downloads/
public_url_base = https://example.com/apps
```

A project selects the section by name:

```ini
[FTP]
profile = kobjolke.com - apps
remote_filename = myapp.apk
```

A profile may contain any `[FTP]` key. Keys in the project's own `[FTP]`
section override the profile, which lets projects share a login and remote path
while keeping their own `remote_filename`.

The profiles path is derived from the installed package location, not the
current working directory. A named profile fails fast when `ftp_profiles.ini`
is missing or when its section is unknown; the latter error lists the available
profile names. Configurations without `profile` keep working without reading the
profiles file.

## Check all profiles

Run this from a shell with the release tool installed:

```bash
release-tool check-ftp
```

From this checkout, `tools\check_ftp.bat` runs the same check and accepts the same options:

```bat
tools\check_ftp.bat
```

The command checks every section in `ftp_profiles.ini` by connecting, logging in,
and opening its configured `remote_path`. It is read-only: it does not create
missing folders or upload, delete, or change files. Each profile prints an
`OK` or `FAIL` line, followed by a summary. Connection attempts time out after
15 seconds by default.

Use `--profiles <path>` to check a different INI file or
`--timeout <seconds>` to change the connection timeout. Add `--verbose` for
debug logging. The command exits with 0 when all profiles pass, 1 when one or
more profiles fail, or 2 when the profiles file is missing or contains no
profiles. Failed profile output redacts its configured password.
