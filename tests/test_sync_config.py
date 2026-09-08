"""Tests for the `sync` command configuration."""

from pathlib import Path

import pytest

from release_tool.exceptions import ConfigurationError
from release_tool.sync_config import SyncConfig

MINIMAL = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /

[Sync]
local_dir = releases
"""


def write_ini(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "sync.ini"
    path.write_text(content, encoding="utf-8")
    return path


class TestSyncConfig:
    """Tests for SyncConfig.from_ini_file."""

    def test_minimal_config_applies_defaults(self, tmp_path: Path) -> None:
        """local_dir alone is enough; exclude is empty and skip_unchanged is on."""
        config = SyncConfig.from_ini_file(write_ini(tmp_path, MINIMAL))

        assert config.ftp.host == "ftp.example.com"
        assert config.local_dir == Path("releases")
        assert config.exclude == []
        assert config.skip_unchanged is True

    def test_exclude_is_split_and_trimmed(self, tmp_path: Path) -> None:
        """Comma-separated globs become a trimmed list."""
        content = MINIMAL + "exclude = windows/** ,  *.tmp\nskip_unchanged = false\n"
        config = SyncConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.exclude == ["windows/**", "*.tmp"]
        assert config.skip_unchanged is False

    def test_missing_sync_section_raises(self, tmp_path: Path) -> None:
        """A config without [Sync] is not a sync config."""
        content = MINIMAL.split("[Sync]")[0]
        with pytest.raises(ConfigurationError, match=r"\[Sync\]"):
            SyncConfig.from_ini_file(write_ini(tmp_path, content))

    def test_missing_local_dir_raises(self, tmp_path: Path) -> None:
        """local_dir is the one required key."""
        content = MINIMAL.replace("local_dir = releases", "")
        with pytest.raises(ConfigurationError, match="local_dir"):
            SyncConfig.from_ini_file(write_ini(tmp_path, content))

    def test_remote_filename_is_rejected(self, tmp_path: Path) -> None:
        """A single-file rename has no meaning for a directory sync — fail loudly."""
        content = MINIMAL.replace("remote_path = /", "remote_path = /\nremote_filename = app.apk")
        with pytest.raises(ConfigurationError, match="remote_filename"):
            SyncConfig.from_ini_file(write_ini(tmp_path, content))

    def test_ftp_validation_is_shared(self, tmp_path: Path) -> None:
        """The [FTP] rules are the same ones the other commands enforce."""
        content = MINIMAL.replace("host = ftp.example.com", "host =")
        with pytest.raises(ConfigurationError, match="host"):
            SyncConfig.from_ini_file(write_ini(tmp_path, content))
