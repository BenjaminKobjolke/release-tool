"""Configuration for the `android` command (build + upload an APK)."""

import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .config import ReleaseConfig, load_parser

# Reused rather than duplicated so every boolean option in the tool fails the same way.
from .create_config import _getboolean
from .exceptions import ConfigurationError
from .version_file import DEFAULT_VERSION_FILE, DEFAULT_VERSION_FORMAT, validate_version_format

BUILD_SECTION = "Build"

DEFAULT_COMMAND = "fvm flutter build apk --release"
DEFAULT_COMMAND_DEBUG = "fvm flutter build apk --debug"
DEFAULT_APK = "build/app/outputs/flutter-apk/app-release.apk"
DEFAULT_APK_DEBUG = "build/app/outputs/flutter-apk/app-debug.apk"
DEFAULT_BUMP_ON_DEBUG = False

DEBUG_SUFFIX = "-debug"


@dataclass(frozen=True)
class BuildVariant:
    """Everything one `android` run needs, all derived from the debug flag alone."""

    command: list[str]
    apk: Path
    remote_filename: str
    bump: bool
    public_url: str | None


@dataclass
class AndroidConfig:
    """Complete configuration for the `android` command."""

    release: ReleaseConfig
    command: list[str]
    command_debug: list[str]
    apk: Path
    apk_debug: Path
    version_file: Path
    version_file_format: str
    bump_on_debug: bool

    def variant(self, debug: bool) -> BuildVariant:
        """Resolve the one determinant — debug or release — into every dependent value."""
        remote_filename = self._remote_filename(debug)
        base = self.release.ftp.public_url_base
        return BuildVariant(
            command=self.command_debug if debug else self.command,
            apk=self.apk_debug if debug else self.apk,
            remote_filename=remote_filename,
            bump=self.bump_on_debug if debug else True,
            public_url=f"{base.rstrip('/')}/{remote_filename}" if base else None,
        )

    def _remote_filename(self, debug: bool) -> str:
        """Debug uploads sit beside the release ones under a `-debug` name."""
        name = self.release.ftp.remote_filename
        assert name is not None  # from_ini_file() requires it
        if not debug:
            return name
        stem, _, suffix = name.rpartition(".")
        return f"{stem}{DEBUG_SUFFIX}.{suffix}" if stem else f"{name}{DEBUG_SUFFIX}"

    @classmethod
    def from_ini_file(cls, path: Path) -> "AndroidConfig":
        """Load configuration from INI file."""
        parser = load_parser(path)
        release = ReleaseConfig.from_parser(parser)

        if not release.ftp.remote_filename:
            raise ConfigurationError(
                "FTP remote_filename is required for the android command — "
                "it is the name the APK gets on the server (e.g. tickets.apk)."
            )
        if release.pre_sign:
            raise ConfigurationError(
                "PreSigning is not supported for the android command: Authenticode signing "
                "does not apply to an APK and the signer wait would block until it times out."
            )

        # has_section rather than `in`: ConfigParser.get is (section, option), not dict.get.
        section: Mapping[str, str] = (
            parser[BUILD_SECTION] if parser.has_section(BUILD_SECTION) else {}
        )
        return cls(
            release=release,
            command=_split_command(section.get("command", DEFAULT_COMMAND), "command"),
            command_debug=_split_command(
                section.get("command_debug", DEFAULT_COMMAND_DEBUG), "command_debug"
            ),
            apk=Path(section.get("apk", DEFAULT_APK)),
            apk_debug=Path(section.get("apk_debug", DEFAULT_APK_DEBUG)),
            version_file=Path(section.get("version_file", DEFAULT_VERSION_FILE)),
            version_file_format=_version_format(
                section.get("version_file_format", DEFAULT_VERSION_FORMAT)
            ),
            bump_on_debug=_getboolean(
                parser, BUILD_SECTION, "bump_on_debug", DEFAULT_BUMP_ON_DEBUG
            ),
        )


def _split_command(raw: str, key: str) -> list[str]:
    """Parse an INI command string into argv, honouring quotes.

    posix=False because this is a Windows tool: a backslash is a path separator,
    not an escape, so `tools\\build.bat` must survive intact. That mode leaves the
    quotes on a quoted token, so they are stripped here.
    """
    try:
        command = [_unquote(part) for part in shlex.split(raw, posix=False)]
    except ValueError as e:
        raise ConfigurationError(f"Invalid '{key}' value: {e}") from e
    if not command:
        raise ConfigurationError(f"Build '{key}' must not be empty")
    return command


def _unquote(part: str) -> str:
    """Drop the surrounding quotes shlex leaves on a token in non-posix mode."""
    for quote in ('"', "'"):
        if len(part) >= 2 and part.startswith(quote) and part.endswith(quote):
            return part[1:-1]
    return part


def _version_format(raw: str) -> str:
    """Validate here, not at bump time after a build already ran."""
    try:
        return validate_version_format(raw)
    except ConfigurationError as e:
        raise ConfigurationError(f"Invalid 'version_file_format' value: {e}") from e
