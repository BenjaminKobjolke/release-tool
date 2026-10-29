"""Tests for remote release filenames."""

from pathlib import Path
from unittest.mock import patch

import pytest

from release_tool.config import (
    FTPConfig,
    OldFileConfig,
    OldFilePolicy,
    ReleaseConfig,
    SubfolderNaming,
)
from release_tool.exceptions import ConfigurationError
from release_tool.release_manager import ReleaseManager


class TestReleaseManagerRemoteNames:
    @pytest.mark.parametrize(
        "override", ["nested/tickets.apk", r"nested\tickets.apk"]
    )
    def test_release_rejects_remote_filename_override_with_path(
        self, tmp_path: Path, override: str
    ) -> None:
        """Per-release names cannot bypass the configured bare-filename rule."""
        test_file = tmp_path / "app.apk"
        test_file.write_bytes(b"content")
        manager = ReleaseManager(
            ReleaseConfig(
                ftp=FTPConfig(
                    host="ftp.example.com",
                    port=21,
                    username="testuser",
                    password="testpass",
                    remote_path="/downloads",
                ),
                old_file=OldFileConfig(
                    policy=OldFilePolicy.DELETE,
                    subfolder_base="old_versions",
                    subfolder_naming=SubfolderNaming.TIMESTAMP,
                ),
            ),
            dry_run=True,
        )

        with pytest.raises(
            ConfigurationError, match="remote_filename must be a bare filename"
        ):
            manager.release(test_file, remote_filename=override)

    @pytest.mark.parametrize(
        ("local_name", "override", "expected_remote_name"),
        [
            ("app-release.apk", None, "tickets.apk"),
            ("app-debug.apk", "tickets-debug.apk", "tickets-debug.apk"),
        ],
    )
    def test_release_uses_effective_remote_filename(
        self,
        tmp_path: Path,
        local_name: str,
        override: str | None,
        expected_remote_name: str,
    ) -> None:
        """The override wins over configuration and otherwise uses configuration."""
        test_file = tmp_path / local_name
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
            result = manager.release(test_file, remote_filename=override)

        assert result is True
        # The server operations must all use the selected remote name.
        mock_exists.assert_called_once_with(expected_remote_name)
        mock_handle.assert_called_once_with(manager.client, expected_remote_name, None)
        mock_upload.assert_called_once_with(test_file, expected_remote_name)

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
