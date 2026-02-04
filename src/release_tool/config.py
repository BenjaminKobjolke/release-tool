"""Configuration dataclasses and parsing."""

import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .exceptions import ConfigurationError
from .pre_signer import PreSignConfig


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


@dataclass
class OldFileConfig:
    """Configuration for handling old files."""

    policy: OldFilePolicy
    subfolder_base: str
    subfolder_naming: SubfolderNaming


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
        if not path.exists():
            raise ConfigurationError(f"Configuration file not found: {path}")

        parser = configparser.ConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except configparser.Error as e:
            raise ConfigurationError(f"Failed to parse configuration file: {e}") from e

        # Parse FTP section
        if "FTP" not in parser:
            raise ConfigurationError("Missing [FTP] section in configuration")

        ftp_section = parser["FTP"]
        try:
            ftp_config = FTPConfig(
                host=ftp_section.get("host", ""),
                port=ftp_section.getint("port", 21),
                username=ftp_section.get("username", ""),
                password=ftp_section.get("password", ""),
                remote_path=ftp_section.get("remote_path", "/"),
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid FTP configuration: {e}") from e

        if not ftp_config.host:
            raise ConfigurationError("FTP host is required")
        if not ftp_config.username:
            raise ConfigurationError("FTP username is required")

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

        # Parse PreSigning section (optional)
        pre_sign_config = None
        if "PreSigning" in parser:
            pre_sign_section = parser["PreSigning"]
            enabled = pre_sign_section.getboolean("enabled", False)
            if enabled:
                network_path = pre_sign_section.get("network_path", "")
                if not network_path:
                    raise ConfigurationError(
                        "PreSigning network_path is required when enabled"
                    )
                network_path_signed = pre_sign_section.get("network_path_signed", "")
                if not network_path_signed:
                    raise ConfigurationError(
                        "PreSigning network_path_signed is required when enabled"
                    )
                expected_signer = pre_sign_section.get("expected_signer", "")
                if not expected_signer:
                    raise ConfigurationError(
                        "PreSigning expected_signer is required when enabled"
                    )
                try:
                    pre_sign_config = PreSignConfig(
                        enabled=True,
                        network_path=network_path,
                        network_path_signed=network_path_signed,
                        expected_signer=expected_signer,
                        poll_interval=pre_sign_section.getint("poll_interval", 10),
                        timeout=pre_sign_section.getint("timeout", 300),
                    )
                except ValueError as e:
                    raise ConfigurationError(
                        f"Invalid PreSigning configuration: {e}"
                    ) from e

        # Parse ReleaseNotes section (optional)
        release_notes_config = None
        if "ReleaseNotes" in parser:
            release_notes_section = parser["ReleaseNotes"]
            path = release_notes_section.get("path", "")
            remote_path = release_notes_section.get("remote_path", "")
            if path and remote_path:
                release_notes_config = ReleaseNotesConfig(
                    path=path,
                    remote_path=remote_path,
                )
            elif path or remote_path:
                raise ConfigurationError(
                    "ReleaseNotes requires both 'path' and 'remote_path'"
                )

        return cls(
            ftp=ftp_config,
            old_file=old_file_config,
            pre_sign=pre_sign_config,
            release_notes=release_notes_config,
        )
