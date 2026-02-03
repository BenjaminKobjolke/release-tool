"""Tests for release manager module."""

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


class TestReleaseManager:
    """Tests for ReleaseManager class."""

    @pytest.fixture
    def release_config(self) -> ReleaseConfig:
        """Create test release configuration."""
        return ReleaseConfig(
            ftp=FTPConfig(
                host="ftp.example.com",
                port=21,
                username="testuser",
                password="testpass",
                remote_path="/releases",
            ),
            old_file=OldFileConfig(
                policy=OldFilePolicy.DELETE,
                subfolder_base="old_versions",
                subfolder_naming=SubfolderNaming.TIMESTAMP,
            ),
        )

    def test_release_file_not_found(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test release fails when file doesn't exist."""
        manager = ReleaseManager(release_config)
        nonexistent = tmp_path / "nonexistent.exe"

        result = manager.release(nonexistent)

        assert result is False

    def test_dry_run_release(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test dry run doesn't connect to FTP."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config, dry_run=True)

        with patch.object(manager.client, "connect") as mock_connect:
            result = manager.release(test_file)

            assert result is True
            mock_connect.assert_not_called()

    def test_release_new_file(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test releasing a new file (no existing file on remote)."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config)

        with patch.object(manager.client, "connect"):
            with patch.object(manager.client, "disconnect"):
                with patch.object(
                    manager.client, "file_exists", return_value=False
                ) as mock_exists:
                    with patch.object(manager.client, "upload_file") as mock_upload:
                        result = manager.release(test_file)

        assert result is True
        mock_exists.assert_called_once_with("test.exe")
        mock_upload.assert_called_once_with(test_file)

    def test_release_existing_file_delete_policy(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test releasing when existing file should be deleted."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config)

        with patch.object(manager.client, "connect"):
            with patch.object(manager.client, "disconnect"):
                with patch.object(
                    manager.client, "file_exists", return_value=True
                ):
                    with patch.object(
                        manager.old_file_handler, "handle"
                    ) as mock_handle:
                        with patch.object(manager.client, "upload_file"):
                            result = manager.release(test_file)

        assert result is True
        mock_handle.assert_called_once_with(manager.client, "test.exe", None)

    def test_release_with_version(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test releasing with version for backup naming."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config, version="1.2.3")

        with patch.object(manager.client, "connect"):
            with patch.object(manager.client, "disconnect"):
                with patch.object(
                    manager.client, "file_exists", return_value=True
                ):
                    with patch.object(
                        manager.old_file_handler, "handle"
                    ) as mock_handle:
                        with patch.object(manager.client, "upload_file"):
                            result = manager.release(test_file)

        assert result is True
        mock_handle.assert_called_once_with(manager.client, "test.exe", "1.2.3")

    def test_release_uses_context_manager(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test release uses connection context manager."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config)

        with patch.object(manager.client, "connection") as mock_connection:
            mock_cm = MagicMock()
            mock_connection.return_value.__enter__ = MagicMock(return_value=mock_cm)
            mock_connection.return_value.__exit__ = MagicMock(return_value=False)

            with patch.object(manager.client, "file_exists", return_value=False):
                with patch.object(manager.client, "upload_file"):
                    manager.release(test_file)

            mock_connection.assert_called_once()
