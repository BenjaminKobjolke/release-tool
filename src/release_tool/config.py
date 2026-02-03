"""Configuration dataclasses and parsing."""

import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .exceptions import ConfigurationError


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

        return cls(ftp=ftp_config, old_file=old_file_config)
