"""Configuration for the `sync` command (mirror a local directory tree to FTP)."""

from dataclasses import dataclass
from pathlib import Path

from .config import FTPConfig, load_parser, parse_ftp_config

# Reused rather than duplicated so every list/boolean option in the tool parses
# and fails the same way.
from .create_config import _getboolean, _split_list
from .exceptions import ConfigurationError

SYNC_SECTION = "Sync"

DEFAULT_SKIP_UNCHANGED = True


@dataclass
class SyncConfig:
    """Complete configuration for the `sync` command."""

    ftp: FTPConfig
    local_dir: Path
    exclude: list[str]
    skip_unchanged: bool

    @classmethod
    def from_ini_file(cls, path: Path) -> "SyncConfig":
        """Load configuration from INI file."""
        parser = load_parser(path)
        ftp = parse_ftp_config(parser)

        if ftp.remote_filename:
            raise ConfigurationError(
                "FTP remote_filename has no meaning for the sync command — it uploads a "
                "whole tree, so every file keeps its own name. Remove the key."
            )

        if not parser.has_section(SYNC_SECTION):
            raise ConfigurationError(f"Missing [{SYNC_SECTION}] section in configuration")

        section = parser[SYNC_SECTION]
        local_dir = section.get("local_dir", "").strip()
        if not local_dir:
            raise ConfigurationError("Sync 'local_dir' is required")

        return cls(
            ftp=ftp,
            local_dir=Path(local_dir),
            exclude=_split_list(section.get("exclude", "")),
            skip_unchanged=_getboolean(
                parser, SYNC_SECTION, "skip_unchanged", DEFAULT_SKIP_UNCHANGED
            ),
        )
