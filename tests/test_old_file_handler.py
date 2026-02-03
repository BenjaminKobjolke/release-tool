"""Tests for old file handler module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from release_tool.config import OldFileConfig, OldFilePolicy, SubfolderNaming
from release_tool.ftp_client import FTPClient
from release_tool.old_file_handler import (
    DeleteHandler,
    RenameHandler,
    create_handler,
)


class TestDeleteHandler:
    """Tests for DeleteHandler class."""

    def test_handle_deletes_file(self) -> None:
        """Test that handler deletes the file."""
        mock_client = MagicMock(spec=FTPClient)
        handler = DeleteHandler()

        handler.handle(mock_client, "test.exe", None)

        mock_client.delete_file.assert_called_once_with("test.exe")


class TestRenameHandler:
    """Tests for RenameHandler class."""

    def test_handle_with_timestamp_naming(self) -> None:
        """Test rename with timestamp naming."""
        mock_client = MagicMock(spec=FTPClient)
        handler = RenameHandler("old_versions", SubfolderNaming.TIMESTAMP)

        with patch("release_tool.old_file_handler.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15, 10, 30, 45)

            handler.handle(mock_client, "test.exe", None)

        mock_client.ensure_directory.assert_any_call("old_versions")
        mock_client.ensure_directory.assert_any_call("old_versions/20240115_103045")
        mock_client.rename_file.assert_called_once_with(
            "test.exe", "old_versions/20240115_103045/test.exe"
        )

    def test_handle_with_version_naming(self) -> None:
        """Test rename with version naming."""
        mock_client = MagicMock(spec=FTPClient)
        handler = RenameHandler("backups", SubfolderNaming.VERSION)

        handler.handle(mock_client, "app.exe", "1.2.3")

        mock_client.ensure_directory.assert_any_call("backups")
        mock_client.ensure_directory.assert_any_call("backups/1.2.3")
        mock_client.rename_file.assert_called_once_with(
            "app.exe", "backups/1.2.3/app.exe"
        )

    def test_handle_version_naming_no_version_falls_back_to_timestamp(self) -> None:
        """Test version naming falls back to timestamp when no version provided."""
        mock_client = MagicMock(spec=FTPClient)
        handler = RenameHandler("old_versions", SubfolderNaming.VERSION)

        with patch("release_tool.old_file_handler.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 6, 20, 14, 0, 0)

            handler.handle(mock_client, "test.exe", None)

        mock_client.ensure_directory.assert_any_call("old_versions/20240620_140000")
        mock_client.rename_file.assert_called_once_with(
            "test.exe", "old_versions/20240620_140000/test.exe"
        )


class TestCreateHandler:
    """Tests for create_handler factory function."""

    def test_creates_delete_handler(self) -> None:
        """Test factory creates DeleteHandler for DELETE policy."""
        config = OldFileConfig(
            policy=OldFilePolicy.DELETE,
            subfolder_base="old_versions",
            subfolder_naming=SubfolderNaming.TIMESTAMP,
        )

        handler = create_handler(config)

        assert isinstance(handler, DeleteHandler)

    def test_creates_rename_handler(self) -> None:
        """Test factory creates RenameHandler for RENAME policy."""
        config = OldFileConfig(
            policy=OldFilePolicy.RENAME,
            subfolder_base="backups",
            subfolder_naming=SubfolderNaming.VERSION,
        )

        handler = create_handler(config)

        assert isinstance(handler, RenameHandler)
        assert handler.subfolder_base == "backups"
        assert handler.naming == SubfolderNaming.VERSION
