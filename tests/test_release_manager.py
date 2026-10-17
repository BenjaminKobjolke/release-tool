"""Tests for release manager module."""

from dataclasses import replace
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
from release_tool.pre_signer import PreSignConfig, PreSignMethod, PreSigner
from release_tool.release_manager import ReleaseManager
from release_tool.remote_pre_signer import RemotePreSigner


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

    def test_release_file_not_found(self, release_config: ReleaseConfig, tmp_path: Path) -> None:
        """Test release fails when file doesn't exist."""
        manager = ReleaseManager(release_config)
        nonexistent = tmp_path / "nonexistent.exe"

        result = manager.release(nonexistent)

        assert result is False

    def test_manager_selects_configured_pre_signer(self, release_config: ReleaseConfig) -> None:
        network_config = replace(
            release_config,
            pre_sign=PreSignConfig(
                enabled=True,
                expected_signer="Example GmbH",
                network_path="\\\\server\\unsigned",
                network_path_signed="\\\\server\\signed",
            ),
        )
        remote_config = replace(
            release_config,
            pre_sign=PreSignConfig(
                enabled=True,
                expected_signer="Example GmbH",
                method=PreSignMethod.REMOTE,
                signer_dir="D:\\Tools\\signer",
            ),
        )

        assert isinstance(ReleaseManager(network_config).pre_signer, PreSigner)
        assert isinstance(ReleaseManager(remote_config).pre_signer, RemotePreSigner)

    def test_remote_dry_run_logs_command_without_running_signer(
        self, release_config: ReleaseConfig, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        test_file = tmp_path / "release.exe"
        test_file.write_bytes(b"content")
        config = replace(
            release_config,
            pre_sign=PreSignConfig(
                enabled=True,
                expected_signer="Example GmbH",
                method=PreSignMethod.REMOTE,
                signer_dir=str(tmp_path / "Signer Directory"),
            ),
        )
        manager = ReleaseManager(config, dry_run=True)
        caplog.set_level("INFO")

        with patch("release_tool.remote_pre_signer.subprocess.Popen") as popen:
            assert manager.release(test_file) is True

        assert "sign.bat" in caplog.text
        assert "SIGNER_NO_PAUSE=1" in caplog.text
        assert "Expected signer: Example GmbH" in caplog.text
        popen.assert_not_called()

    def test_network_dry_run_keeps_network_share_details(
        self, release_config: ReleaseConfig, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        test_file = tmp_path / "release.exe"
        test_file.write_bytes(b"content")
        config = replace(
            release_config,
            pre_sign=PreSignConfig(
                enabled=True,
                expected_signer="Example GmbH",
                network_path="\\\\server\\unsigned",
                network_path_signed="\\\\server\\signed",
            ),
        )
        manager = ReleaseManager(config, dry_run=True)
        caplog.set_level("INFO")

        assert manager.release(test_file) is True

        assert "Would copy release.exe to \\\\server\\unsigned" in caplog.text
        assert "Would wait for signed file at: \\\\server\\signed" in caplog.text

    def test_dry_run_release(self, release_config: ReleaseConfig, tmp_path: Path) -> None:
        """Test dry run doesn't connect to FTP."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config, dry_run=True)

        with patch.object(manager.client, "connect") as mock_connect:
            result = manager.release(test_file)

            assert result is True
            mock_connect.assert_not_called()

    def test_release_new_file(self, release_config: ReleaseConfig, tmp_path: Path) -> None:
        """Test releasing a new file (no existing file on remote)."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config)

        with (
            patch.object(manager.client, "connect"),
            patch.object(manager.client, "disconnect"),
            patch.object(manager.client, "file_exists", return_value=False) as mock_exists,
            patch.object(manager.client, "upload_file") as mock_upload,
        ):
            result = manager.release(test_file)

        assert result is True
        mock_exists.assert_called_once_with("test.exe")
        mock_upload.assert_called_once_with(test_file, "test.exe")

    def test_release_existing_file_delete_policy(
        self, release_config: ReleaseConfig, tmp_path: Path
    ) -> None:
        """Test releasing when existing file should be deleted."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config)

        with (
            patch.object(manager.client, "connect"),
            patch.object(manager.client, "disconnect"),
            patch.object(manager.client, "file_exists", return_value=True),
            patch.object(manager.old_file_handler, "handle") as mock_handle,
            patch.object(manager.client, "upload_file"),
        ):
            result = manager.release(test_file)

        assert result is True
        mock_handle.assert_called_once_with(manager.client, "test.exe", None)

    def test_release_with_version(self, release_config: ReleaseConfig, tmp_path: Path) -> None:
        """Test releasing with version for backup naming."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(release_config, version="1.2.3")

        with (
            patch.object(manager.client, "connect"),
            patch.object(manager.client, "disconnect"),
            patch.object(manager.client, "file_exists", return_value=True),
            patch.object(manager.old_file_handler, "handle") as mock_handle,
            patch.object(manager.client, "upload_file"),
        ):
            result = manager.release(test_file)

        assert result is True
        mock_handle.assert_called_once_with(manager.client, "test.exe", "1.2.3")

    def test_release_uses_remote_filename(self, tmp_path: Path) -> None:
        """remote_filename renames on upload and drives the existing-file handling."""
        test_file = tmp_path / "app-release.apk"
        test_file.write_bytes(b"content")

        config = ReleaseConfig(
            ftp=FTPConfig(
                host="ftp.example.com",
                port=21,
                username="testuser",
                password="testpass",
                remote_path="/downloads",
                remote_filename="tickets.apk",
            ),
            old_file=OldFileConfig(
                policy=OldFilePolicy.DELETE,
                subfolder_base="old_versions",
                subfolder_naming=SubfolderNaming.TIMESTAMP,
            ),
        )
        manager = ReleaseManager(config)

        with (
            patch.object(manager.client, "connect"),
            patch.object(manager.client, "disconnect"),
            patch.object(manager.client, "file_exists", return_value=True) as mock_exists,
            patch.object(manager.old_file_handler, "handle") as mock_handle,
            patch.object(manager.client, "upload_file") as mock_upload,
        ):
            result = manager.release(test_file)

        assert result is True
        # The remote holds tickets.apk — checking or renaming app-release.apk would 550.
        mock_exists.assert_called_once_with("tickets.apk")
        mock_handle.assert_called_once_with(manager.client, "tickets.apk", None)
        mock_upload.assert_called_once_with(test_file, "tickets.apk")

    def test_release_remote_filename_override_wins(self, tmp_path: Path) -> None:
        """A per-release name overrides the configured remote filename."""
        test_file = tmp_path / "app-debug.apk"
        test_file.write_bytes(b"content")
        config = ReleaseConfig(
            ftp=FTPConfig(
                host="ftp.example.com",
                port=21,
                username="testuser",
                password="testpass",
                remote_path="/downloads",
                remote_filename="tickets.apk",
            ),
            old_file=OldFileConfig(
                policy=OldFilePolicy.DELETE,
                subfolder_base="old_versions",
                subfolder_naming=SubfolderNaming.TIMESTAMP,
            ),
        )
        manager = ReleaseManager(config)

        with (
            patch.object(manager.client, "connect"),
            patch.object(manager.client, "disconnect"),
            patch.object(manager.client, "file_exists", return_value=True) as mock_exists,
            patch.object(manager.old_file_handler, "handle") as mock_handle,
            patch.object(manager.client, "upload_file") as mock_upload,
        ):
            result = manager.release(test_file, remote_filename="tickets-debug.apk")

        assert result is True
        mock_exists.assert_called_once_with("tickets-debug.apk")
        mock_handle.assert_called_once_with(manager.client, "tickets-debug.apk", None)
        mock_upload.assert_called_once_with(test_file, "tickets-debug.apk")

    def test_dry_run_names_override(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Dry-run narration uses the per-release filename override."""
        test_file = tmp_path / "app-debug.apk"
        test_file.write_bytes(b"content")
        config = ReleaseConfig(
            ftp=FTPConfig(
                host="ftp.example.com",
                port=21,
                username="testuser",
                password="testpass",
                remote_path="/downloads",
                remote_filename="tickets.apk",
            ),
            old_file=OldFileConfig(
                policy=OldFilePolicy.DELETE,
                subfolder_base="old_versions",
                subfolder_naming=SubfolderNaming.TIMESTAMP,
            ),
        )
        manager = ReleaseManager(config, dry_run=True)
        caplog.set_level("INFO")

        with patch.object(manager.client, "connect") as mock_connect:
            assert manager.release(test_file, remote_filename="tickets-debug.apk") is True

        assert "Would check if tickets-debug.apk exists on remote" in caplog.text
        assert f"Would upload {test_file} as tickets-debug.apk" in caplog.text
        mock_connect.assert_not_called()

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

            with (
                patch.object(manager.client, "file_exists", return_value=False),
                patch.object(manager.client, "upload_file"),
            ):
                manager.release(test_file)

            mock_connection.assert_called_once()

    def test_release_version_exists_aborted(self, tmp_path: Path) -> None:
        """Test release aborts when version exists and user declines overwrite."""
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
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(config, version="1.0.0")

        with patch.object(manager.client, "connection") as mock_connection:
            mock_cm = MagicMock()
            mock_connection.return_value.__enter__ = MagicMock(return_value=mock_cm)
            mock_connection.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch.object(manager.client, "directory_exists", return_value=True),
                patch("builtins.input", return_value="n"),
            ):
                result = manager.release(test_file)

        assert result is False

    def test_release_version_exists_overwrite(self, tmp_path: Path) -> None:
        """Test release continues when version exists and user confirms overwrite."""
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
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(config, version="1.0.0")

        with patch.object(manager.client, "connection") as mock_connection:
            mock_cm = MagicMock()
            mock_connection.return_value.__enter__ = MagicMock(return_value=mock_cm)
            mock_connection.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch.object(manager.client, "directory_exists", return_value=True),
                patch("builtins.input", return_value="y"),
                patch.object(manager.client, "file_exists", return_value=False),
                patch.object(manager.client, "upload_file"),
            ):
                result = manager.release(test_file)

        assert result is True

    def test_release_version_not_exists_no_prompt(self, tmp_path: Path) -> None:
        """Test release proceeds without prompt when version doesn't exist."""
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
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        manager = ReleaseManager(config, version="2.0.0")

        with patch.object(manager.client, "connection") as mock_connection:
            mock_cm = MagicMock()
            mock_connection.return_value.__enter__ = MagicMock(return_value=mock_cm)
            mock_connection.return_value.__exit__ = MagicMock(return_value=False)

            with (
                patch.object(manager.client, "directory_exists", return_value=False),
                patch("builtins.input") as mock_input,
            ):
                with (
                    patch.object(manager.client, "file_exists", return_value=False),
                    patch.object(manager.client, "upload_file"),
                ):
                    result = manager.release(test_file)

                mock_input.assert_not_called()

        assert result is True
