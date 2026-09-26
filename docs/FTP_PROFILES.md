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
