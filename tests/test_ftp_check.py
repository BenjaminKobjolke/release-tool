"""Tests for checking configured FTP profiles."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from release_tool.config import FTPConfig
from release_tool.exceptions import ConfigurationError, FTPError
from release_tool.ftp_check import ProfileCheckResult, check_profiles
from release_tool.ftp_client import FTPClient


def _write_profiles(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_checks_profiles_in_order_and_redacts_password(tmp_path: Path) -> None:
    path = _write_profiles(
        tmp_path / "profiles.ini",
        """[first]
host = first.example.com
username = user
password = secret-one
remote_path = /ok

[second]
host = second.example.com
username = user
password = secret-two
remote_path = /bad
""",
    )
    clients: list[MagicMock] = []

    def make_client(config: FTPConfig) -> FTPClient:
        client = MagicMock(spec=FTPClient)
        if config.host.startswith("second"):
            client.probe.side_effect = FTPError("Login failed: secret-two")
        clients.append(client)
        return client

    results = check_profiles(path, timeout=2, client_factory=make_client)

    assert results == [
        ProfileCheckResult("first", True, "first.example.com:21 /ok"),
        ProfileCheckResult("second", False, "Login failed: [redacted]"),
    ]
    assert len(clients) == 2
    assert all(
        password not in result.detail
        for password in ("secret-one", "secret-two")
        for result in results
    )


def test_invalid_profile_fails_and_next_profile_is_checked(tmp_path: Path) -> None:
    path = _write_profiles(
        tmp_path / "profiles.ini",
        """[broken]
username = user

[good]
host = good.example.com
username = user
""",
    )
    checked_hosts: list[str] = []

    def make_client(config: FTPConfig) -> FTPClient:
        checked_hosts.append(config.host)
        return MagicMock(spec=FTPClient)

    results = check_profiles(path, timeout=1, client_factory=make_client)

    assert [result.ok for result in results] == [False, True]
    assert "FTP host is required" in results[0].detail
    assert results[1].name == "good"
    assert checked_hosts == ["good.example.com"]


def test_missing_profiles_file_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        check_profiles(tmp_path / "missing.ini", timeout=1)


def test_empty_profiles_file_raises_configuration_error(tmp_path: Path) -> None:
    path = _write_profiles(tmp_path / "empty.ini", "")

    with pytest.raises(ConfigurationError, match="No FTP profiles"):
        check_profiles(path, timeout=1)
