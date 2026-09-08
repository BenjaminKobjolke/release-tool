"""Tests for configuration module."""

from pathlib import Path

import pytest

from release_tool.config import (
    FTPConfig,
    OldFileConfig,
    OldFilePolicy,
    ReleaseConfig,
    SubfolderNaming,
)
from release_tool.exceptions import ConfigurationError


class TestFTPConfig:
    """Tests for FTPConfig dataclass."""

    def test_creation(self) -> None:
        """Test basic FTPConfig creation."""
        config = FTPConfig(
            host="ftp.example.com",
            port=21,
            username="user",
            password="pass",
            remote_path="/path",
        )
        assert config.host == "ftp.example.com"
        assert config.port == 21
        assert config.username == "user"
        assert config.password == "pass"
        assert config.remote_path == "/path"


class TestOldFileConfig:
    """Tests for OldFileConfig dataclass."""

    def test_creation_delete_policy(self) -> None:
        """Test OldFileConfig with delete policy."""
        config = OldFileConfig(
            policy=OldFilePolicy.DELETE,
            subfolder_base="backups",
            subfolder_naming=SubfolderNaming.TIMESTAMP,
        )
        assert config.policy == OldFilePolicy.DELETE

    def test_creation_rename_policy(self) -> None:
        """Test OldFileConfig with rename policy."""
        config = OldFileConfig(
            policy=OldFilePolicy.RENAME,
            subfolder_base="old_versions",
            subfolder_naming=SubfolderNaming.VERSION,
        )
        assert config.policy == OldFilePolicy.RENAME
        assert config.subfolder_naming == SubfolderNaming.VERSION


class TestReleaseConfig:
    """Tests for ReleaseConfig class."""

    def test_from_ini_file_valid(self, tmp_path: Path) -> None:
        """Test loading valid configuration file."""
        config_content = """[FTP]
host = ftp.example.com
port = 2121
username = testuser
password = testpass
remote_path = /releases/app

[OldFileHandling]
policy = rename
subfolder_base = backups
subfolder_naming = version
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        config = ReleaseConfig.from_ini_file(config_path)

        assert config.ftp.host == "ftp.example.com"
        assert config.ftp.port == 2121
        assert config.ftp.username == "testuser"
        assert config.ftp.password == "testpass"
        assert config.ftp.remote_path == "/releases/app"
        assert config.old_file.policy == OldFilePolicy.RENAME
        assert config.old_file.subfolder_base == "backups"
        assert config.old_file.subfolder_naming == SubfolderNaming.VERSION

    def test_from_ini_file_minimal(self, tmp_path: Path) -> None:
        """Test loading minimal configuration file."""
        config_content = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        config = ReleaseConfig.from_ini_file(config_path)

        assert config.ftp.host == "ftp.example.com"
        assert config.ftp.port == 21  # default
        assert config.ftp.remote_path == "/"  # default
        assert config.old_file.policy == OldFilePolicy.DELETE  # default
        assert config.old_file.subfolder_naming == SubfolderNaming.TIMESTAMP  # default

    def test_from_ini_file_remote_naming_defaults_to_none(self, tmp_path: Path) -> None:
        """Without the keys, upload keeps using the local filename."""
        config_content = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        config = ReleaseConfig.from_ini_file(config_path)

        assert config.ftp.remote_filename is None
        assert config.ftp.public_url_base is None

    def test_from_ini_file_remote_naming(self, tmp_path: Path) -> None:
        """remote_filename and public_url_base are read from [FTP]."""
        config_content = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_filename = tickets.apk
public_url_base = https://example.com/apps
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        config = ReleaseConfig.from_ini_file(config_path)

        assert config.ftp.remote_filename == "tickets.apk"
        assert config.ftp.public_url_base == "https://example.com/apps"

    @pytest.mark.parametrize("value", ["/downloads/tickets.apk", "sub\\tickets.apk"])
    def test_from_ini_file_remote_filename_rejects_paths(self, tmp_path: Path, value: str) -> None:
        """A directory in remote_filename would silently upload to the wrong place."""
        config_content = f"""[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_filename = {value}
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        with pytest.raises(ConfigurationError, match="remote_filename"):
            ReleaseConfig.from_ini_file(config_path)

    def test_from_ini_file_not_found(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        with pytest.raises(ConfigurationError, match="not found"):
            ReleaseConfig.from_ini_file(tmp_path / "nonexistent.ini")

    def test_from_ini_file_missing_ftp_section(self, tmp_path: Path) -> None:
        """Test error when FTP section is missing."""
        config_path = tmp_path / "config.ini"
        config_path.write_text("[OldFileHandling]\npolicy = delete\n")

        with pytest.raises(ConfigurationError, match="Missing \\[FTP\\] section"):
            ReleaseConfig.from_ini_file(config_path)

    def test_from_ini_file_missing_host(self, tmp_path: Path) -> None:
        """Test error when FTP host is missing."""
        config_content = """[FTP]
username = testuser
password = testpass
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        with pytest.raises(ConfigurationError, match="host is required"):
            ReleaseConfig.from_ini_file(config_path)

    def test_from_ini_file_missing_username(self, tmp_path: Path) -> None:
        """Test error when FTP username is missing."""
        config_content = """[FTP]
host = ftp.example.com
password = testpass
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        with pytest.raises(ConfigurationError, match="username is required"):
            ReleaseConfig.from_ini_file(config_path)

    def test_from_ini_file_invalid_policy(self, tmp_path: Path) -> None:
        """Test error when policy is invalid."""
        config_content = """[FTP]
host = ftp.example.com
username = testuser
password = testpass

[OldFileHandling]
policy = invalid
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        with pytest.raises(ConfigurationError, match="Invalid old file policy"):
            ReleaseConfig.from_ini_file(config_path)

    def test_from_ini_file_invalid_naming(self, tmp_path: Path) -> None:
        """Test error when subfolder_naming is invalid."""
        config_content = """[FTP]
host = ftp.example.com
username = testuser
password = testpass

[OldFileHandling]
policy = rename
subfolder_naming = invalid
"""
        config_path = tmp_path / "config.ini"
        config_path.write_text(config_content)

        with pytest.raises(ConfigurationError, match="Invalid subfolder naming"):
            ReleaseConfig.from_ini_file(config_path)
