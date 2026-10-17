"""Configuration dataclasses and parsing."""

import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .exceptions import ConfigurationError
from .pre_signer import PreSignConfig, PreSignMethod

PROFILES_FILE = Path(__file__).resolve().parents[2] / "ftp_profiles.ini"
PROFILE_KEY = "profile"


@dataclass
class ReleaseNotesConfig:
    """Configuration for release notes upload."""

    path: str  # Local path to release notes folder
    remote_path: str  # FTP remote path for release notes


class OldFilePolicy(Enum):
    """Policy for handling existing files on remote."""

    DELETE = "delete"
    RENAME = "rename"


class SubfolderNaming(Enum):
    """Naming scheme for backup subfolders."""

    TIMESTAMP = "timestamp"
    VERSION = "version"


@dataclass
class FTPConfig:
    """FTP connection configuration."""

    host: str
    port: int
    username: str
    password: str
    remote_path: str
    # Upload under this name instead of the local filename (rclone `copyto` semantics).
    remote_filename: str | None = None
    # Base of the public download URL, for the post-upload summary line.
    public_url_base: str | None = None


@dataclass
class OldFileConfig:
    """Configuration for handling old files."""

    policy: OldFilePolicy
    subfolder_base: str
    subfolder_naming: SubfolderNaming


def load_parser(path: Path) -> configparser.ConfigParser:
    """Read an INI file into a parser, with one shared missing/invalid-file contract."""
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as e:
        raise ConfigurationError(f"Failed to parse configuration file: {e}") from e
    return parser


def _load_ftp_profile(name: str, path: Path) -> dict[str, str]:
    """Load one named profile from the private profiles file."""
    if not path.exists():
        raise ConfigurationError(f"FTP profile '{name}' requested but {path} does not exist")

    parser = load_parser(path)
    if name not in parser:
        available = ", ".join(parser.sections()) or "(none)"
        raise ConfigurationError(
            f"FTP profile '{name}' not found in {path}. Available profiles: {available}"
        )
    return dict(parser[name])


def parse_ftp_config(
    parser: configparser.ConfigParser, profiles_path: Path | None = None
) -> FTPConfig:
    """Parse and validate the [FTP] section.

    Split out of ReleaseConfig so `sync`, which needs the connection but none of
    the single-file release settings, validates credentials the exact same way.
    """
    if "FTP" not in parser:
        raise ConfigurationError("Missing [FTP] section in configuration")

    values = dict(parser["FTP"])
    if PROFILE_KEY in values:
        name = values.pop(PROFILE_KEY).strip()
        path = PROFILES_FILE if profiles_path is None else profiles_path
        values = {**_load_ftp_profile(name, path), **values}

    return build_ftp_config(values)


def build_ftp_config(values: dict[str, str]) -> FTPConfig:
    """Build and validate an FTP configuration from one profile's values."""
    try:
        ftp_config = FTPConfig(
            host=values.get("host", ""),
            port=int(values.get("port", "21")),
            username=values.get("username", ""),
            password=values.get("password", ""),
            remote_path=values.get("remote_path", "/"),
            remote_filename=values.get("remote_filename") or None,
            public_url_base=values.get("public_url_base") or None,
        )
    except ValueError as e:
        raise ConfigurationError(f"Invalid FTP configuration: {e}") from e

    if not ftp_config.host:
        raise ConfigurationError("FTP host is required")
    if not ftp_config.username:
        raise ConfigurationError("FTP username is required")
    # A directory here would silently resolve against the post-cwd() dir instead of
    # remote_path, uploading to the wrong place with no error.
    if ftp_config.remote_filename and (
        "/" in ftp_config.remote_filename or "\\" in ftp_config.remote_filename
    ):
        raise ConfigurationError(
            f"FTP remote_filename must be a bare filename, not a path: "
            f"{ftp_config.remote_filename}. Put the directory in remote_path."
        )

    return ftp_config


@dataclass
class ReleaseConfig:
    """Complete release configuration."""

    ftp: FTPConfig
    old_file: OldFileConfig
    pre_sign: PreSignConfig | None = None
    release_notes: ReleaseNotesConfig | None = None

    @classmethod
    def from_ini_file(cls, path: Path) -> "ReleaseConfig":
        """Load configuration from INI file."""
        return cls.from_parser(load_parser(path))

    @classmethod
    def from_parser(cls, parser: configparser.ConfigParser) -> "ReleaseConfig":
        """Build the configuration from an already-loaded parser.

        Split out so a caller that needs extra sections of the same file — the
        android command's [Build] — reads and parses it once, not twice.
        """
        ftp_config = parse_ftp_config(parser)

        # Parse OldFileHandling section
        old_file_section = parser["OldFileHandling"] if "OldFileHandling" in parser else {}

        policy_str = old_file_section.get("policy", "delete").lower()
        try:
            policy = OldFilePolicy(policy_str)
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid old file policy: {policy_str}. Must be 'delete' or 'rename'"
            ) from e

        naming_str = old_file_section.get("subfolder_naming", "timestamp").lower()
        try:
            naming = SubfolderNaming(naming_str)
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid subfolder naming: {naming_str}. Must be 'timestamp' or 'version'"
            ) from e

        old_file_config = OldFileConfig(
            policy=policy,
            subfolder_base=old_file_section.get("subfolder_base", "old_versions"),
            subfolder_naming=naming,
        )

        pre_sign_config = _parse_pre_sign_config(parser)

        # Parse ReleaseNotes section (optional)
        release_notes_config = None
        if "ReleaseNotes" in parser:
            release_notes_section = parser["ReleaseNotes"]
            notes_path = release_notes_section.get("path", "")
            remote_path = release_notes_section.get("remote_path", "")
            if notes_path and remote_path:
                release_notes_config = ReleaseNotesConfig(
                    path=notes_path,
                    remote_path=remote_path,
                )
            elif notes_path or remote_path:
                raise ConfigurationError("ReleaseNotes requires both 'path' and 'remote_path'")

        return cls(
            ftp=ftp_config,
            old_file=old_file_config,
            pre_sign=pre_sign_config,
            release_notes=release_notes_config,
        )


def _parse_pre_sign_config(parser: configparser.ConfigParser) -> PreSignConfig | None:
    """Parse the optional [PreSigning] section for its selected method."""
    if "PreSigning" not in parser:
        return None

    section = parser["PreSigning"]
    if not section.getboolean("enabled", False):
        return None

    method_value = section.get("method", PreSignMethod.NETWORK.value).lower()
    try:
        method = PreSignMethod(method_value)
    except ValueError as e:
        raise ConfigurationError(
            f"Invalid PreSigning method: {method_value}. Must be 'network' or 'remote'"
        ) from e

    expected_signer = section.get("expected_signer", "")
    values: dict[str, str] = {"expected_signer": expected_signer}
    if method is PreSignMethod.NETWORK:
        values["network_path"] = section.get("network_path", "")
        values["network_path_signed"] = section.get("network_path_signed", "")
        if not values["network_path"]:
            raise ConfigurationError("PreSigning network_path is required when enabled")
        if not values["network_path_signed"]:
            raise ConfigurationError("PreSigning network_path_signed is required when enabled")
        if not expected_signer:
            raise ConfigurationError("PreSigning expected_signer is required when enabled")
    else:
        values["signer_dir"] = section.get("signer_dir", "")
        if not values["signer_dir"]:
            raise ConfigurationError("PreSigning signer_dir is required when enabled")
        if not expected_signer:
            raise ConfigurationError("PreSigning expected_signer is required when enabled")

    try:
        if method is PreSignMethod.NETWORK:
            poll_interval = section.getint("poll_interval", 10)
            timeout = section.getint("timeout", 300)
        else:
            poll_interval = 10
            timeout = 300
        return PreSignConfig(
            enabled=True,
            method=method,
            poll_interval=poll_interval,
            timeout=timeout,
            **values,
        )
    except ValueError as e:
        raise ConfigurationError(f"Invalid PreSigning configuration: {e}") from e
