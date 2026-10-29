"""Tests for configuration module."""

import configparser
from pathlib import Path

import pytest

from release_tool.config import (
    FTPConfig,
    OldFileConfig,
    OldFilePolicy,
    SubfolderNaming,
    _parse_pre_sign_config,
    build_ftp_config,
    parse_ftp_config,
)
from release_tool.exceptions import ConfigurationError
from release_tool.pre_signer import PreSignMethod
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

    def test_build_from_values(self) -> None:
        config = build_ftp_config(
            {
                "host": "ftp.example.com",
                "username": "user",
                "password": "pass",
                "remote_path": "/releases",
            }
        )

        assert config == FTPConfig(
            host="ftp.example.com",
            port=21,
            username="user",
            password="pass",
            remote_path="/releases",
        )

    def test_build_requires_host(self) -> None:
        with pytest.raises(ConfigurationError, match="FTP host is required"):
            build_ftp_config({"username": "user"})

    def test_build_rejects_invalid_port(self) -> None:
        with pytest.raises(ConfigurationError, match="Invalid FTP configuration"):
            build_ftp_config({"host": "ftp.example.com", "username": "user", "port": "nope"})


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

        with pytest.raises(ConfigurationError) as exc_info:
            parse_ftp_config(parser, path)

        assert str(exc_info.value) == f"FTP profile 'apps' requested but {path} does not exist"

    def test_unknown_profile_lists_available_names(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "ftp_profiles.ini")
        parser = self.parser("[FTP]\nprofile = typo\n")

        with pytest.raises(ConfigurationError) as exc_info:
            parse_ftp_config(parser, profiles)

        assert str(exc_info.value) == (
            f"FTP profile 'typo' not found in {profiles}. "
            "Available profiles: kobjolke.com - apps"
        )

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


class TestSigningProfiles:
    """Tests for reusable named pre-signing configuration."""

    @staticmethod
    def parser(content: str) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser.read_string(content)
        return parser

    @staticmethod
    def write_profiles(path: Path, content: str = "") -> Path:
        path.write_text(
            content
            or """[xida remote]
enabled = true
method = remote
signer_dir = D:\\Tools\\SafeNet Signer
expected_signer = Example GmbH
""",
            encoding="utf-8",
        )
        return path

    def test_loads_named_profile(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "signing_profiles.ini")
        parser = self.parser("[PreSigning]\nprofile = xida remote\n")

        config = _parse_pre_sign_config(parser, profiles)

        assert config is not None
        assert config.enabled is True
        assert config.method is PreSignMethod.REMOTE
        assert config.signer_dir == "D:\\Tools\\SafeNet Signer"
        assert config.expected_signer == "Example GmbH"

    def test_project_value_overrides_profile(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "signing_profiles.ini")
        parser = self.parser(
            "[PreSigning]\nprofile = xida remote\nexpected_signer = Project GmbH\n"
        )

        config = _parse_pre_sign_config(parser, profiles)

        assert config is not None
        assert config.expected_signer == "Project GmbH"

    def test_unknown_profile_lists_available_names(self, tmp_path: Path) -> None:
        profiles = self.write_profiles(tmp_path / "signing_profiles.ini")
        parser = self.parser("[PreSigning]\nprofile = typo\n")

        with pytest.raises(ConfigurationError) as exc_info:
            _parse_pre_sign_config(parser, profiles)

        assert str(exc_info.value) == (
            f"Signing profile 'typo' not found in {profiles}. "
            "Available profiles: xida remote"
        )

    def test_missing_profiles_file_names_expected_path(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.ini"
        parser = self.parser("[PreSigning]\nprofile = apps\n")

        with pytest.raises(ConfigurationError) as exc_info:
            _parse_pre_sign_config(parser, path)

        assert str(exc_info.value) == (
            f"Signing profile 'apps' requested but {path} does not exist"
        )

    def test_no_profile_does_not_read_profiles_file(self, tmp_path: Path) -> None:
        parser = self.parser(
            "[PreSigning]\nenabled = true\nmethod = remote\n"
            "signer_dir = D:\\Tools\\Signer\nexpected_signer = Example GmbH\n"
        )

        config = _parse_pre_sign_config(parser, tmp_path / "missing.ini")

        assert config is not None
        assert config.signer_dir == "D:\\Tools\\Signer"
