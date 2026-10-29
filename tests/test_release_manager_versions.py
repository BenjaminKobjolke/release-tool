"""Tests for versioned release confirmation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.config import (
    FTPConfig,
    OldFileConfig,
    OldFilePolicy,
    ReleaseConfig,
    SubfolderNaming,
)
from release_tool.release_manager import ReleaseManager


def _versioned_manager(version: str) -> ReleaseManager:
    config = ReleaseConfig(
        ftp=FTPConfig(
            host="ftp.example.com",
            port=21,
            username="testuser",
            password="testpass",
            remote_path="/releases",
        ),
        old_file=OldFileConfig(
            policy=OldFilePolicy.RENAME,
            subfolder_base="old_versions",
            subfolder_naming=SubfolderNaming.VERSION,
        ),
    )
    return ReleaseManager(config, version=version)


class TestReleaseManagerVersions:
    @pytest.mark.parametrize(
        ("confirmation", "expected_result"), [("n", False), ("y", True)]
    )
    def test_release_version_exists_uses_confirmation(
        self, tmp_path: Path, confirmation: str, expected_result: bool
    ) -> None:
        """Release aborts or proceeds according to the overwrite confirmation."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = _versioned_manager("1.0.0")

        with patch.object(manager.client, "connection") as mock_connection:
            mock_cm = MagicMock(spec=["__enter__", "__exit__"])
            mock_connection.return_value.__enter__ = MagicMock(return_value=mock_cm)
            mock_connection.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch.object(manager.client, "directory_exists", return_value=True),
                patch("builtins.input", return_value=confirmation),
                patch.object(manager.client, "file_exists", return_value=False),
                patch.object(manager.client, "upload_file"),
            ):
                result = manager.release(test_file)

        assert result is expected_result

    def test_release_version_not_exists_no_prompt(self, tmp_path: Path) -> None:
        """Test release proceeds without prompt when version doesn't exist."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = _versioned_manager("2.0.0")

        with patch.object(manager.client, "connection") as mock_connection:
            mock_cm = MagicMock(spec=["__enter__", "__exit__"])
            mock_connection.return_value.__enter__ = MagicMock(return_value=mock_cm)
            mock_connection.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch.object(manager.client, "directory_exists", return_value=False),
                patch("builtins.input") as mock_input,
                patch.object(manager.client, "file_exists", return_value=False),
                patch.object(manager.client, "upload_file"),
            ):
                result = manager.release(test_file)

            mock_input.assert_not_called()

        assert result is True
