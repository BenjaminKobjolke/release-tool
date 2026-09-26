"""Tests for configuration module."""

import configparser
from pathlib import Path

import pytest

from release_tool.config import (
    FTPConfig,
    OldFileConfig,
    OldFilePolicy,
    ReleaseConfig,
    SubfolderNaming,
    parse_ftp_config,
)
from release_tool.exceptions import ConfigurationError
from release_tool.sync_config import SyncConfig


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


class TestFTPProfiles:
    """Tests for reusable named FTP configuration."""

    @staticmethod
    def parser(content: str) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser.read_string(content)
        return parser

    @staticmethod
    def write_profiles(path: Path, content: str = "") -> Path:
        path.write_text(
            content
            or """[kobjolke.com - apps]
host = ftp.example.com
port = 2121
username = deploy
password = secret
remote_path = /downloads/
public_url_base = https://example.com/apps
""",
            encoding="utf-8",
        )
        return path

    def test_loads_named_profile_with_spaces(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "ftp_profiles.ini")
        parser = self.parser("[FTP]\nprofile = kobjolke.com - apps\nremote_filename = app.apk\n")

        config = parse_ftp_config(parser, profiles)

        assert config == FTPConfig(
            host="ftp.example.com",
            port=2121,
            username="deploy",
            password="secret",
            remote_path="/downloads/",
            remote_filename="app.apk",
            public_url_base="https://example.com/apps",
        )

    def test_project_value_overrides_profile(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "ftp_profiles.ini")
        parser = self.parser(
            "[FTP]\nprofile = kobjolke.com - apps\nremote_path = /project/\n"
        )

        assert parse_ftp_config(parser, profiles).remote_path == "/project/"

    def test_missing_profiles_file_names_expected_path(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.ini"
        parser = self.parser("[FTP]\nprofile = apps\n")

        with pytest.raises(ConfigurationError, match=str(path).replace("\\", "\\\\")):
            parse_ftp_config(parser, path)

    def test_unknown_profile_lists_available_names(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "ftp_profiles.ini")
        parser = self.parser("[FTP]\nprofile = typo\n")

        with pytest.raises(ConfigurationError, match="kobjolke.com - apps"):
            parse_ftp_config(parser, profiles)

    def test_no_profile_does_not_read_profiles_file(self, tmp_path: Path) -> None:
        parser = self.parser("[FTP]\nhost = direct.example\nusername = deploy\n")

        config = parse_ftp_config(parser, tmp_path / "missing.ini")

        assert config.host == "direct.example"

    def test_profile_still_requires_host(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(
            tmp_path / "ftp_profiles.ini", "[incomplete]\nusername = deploy\n"
        )
        parser = self.parser("[FTP]\nprofile = incomplete\n")

        with pytest.raises(ConfigurationError, match="FTP host is required"):
            parse_ftp_config(parser, profiles)

    def test_invalid_profile_port_is_configuration_error(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(
            tmp_path / "ftp_profiles.ini",
            "[apps]\nhost = ftp.example.com\nusername = deploy\nport = nope\n",
        )
        parser = self.parser("[FTP]\nprofile = apps\n")

        with pytest.raises(ConfigurationError, match="Invalid FTP configuration"):
            parse_ftp_config(parser, profiles)

    def test_sync_uses_profile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        profiles = self.write_profiles(tmp_path / "ftp_profiles.ini")
        monkeypatch.setattr("release_tool.config.PROFILES_FILE", profiles)
        config_path = tmp_path / "sync.ini"
        config_path.write_text(
            "[FTP]\nprofile = kobjolke.com - apps\n\n[Sync]\nlocal_dir = releases\n",
            encoding="utf-8",
        )

        config = SyncConfig.from_ini_file(config_path)

        assert config.ftp.host == "ftp.example.com"


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
