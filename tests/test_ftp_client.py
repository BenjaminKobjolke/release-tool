"""Tests for FTP client module."""

import ftplib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.config import FTPConfig
from release_tool.ftp_client import FTPClient
from release_tool.exceptions import FTPError


# Store reference to real FTP class before any patching
RealFTP = ftplib.FTP


class TestFTPClient:
    """Tests for FTPClient class."""

    @pytest.fixture
    def ftp_config(self) -> FTPConfig:
        """Create test FTP config."""
        return FTPConfig(
            host="ftp.example.com",
            port=21,
            username="testuser",
            password="testpass",
            remote_path="/releases",
        )

    @pytest.fixture
    def client(self, ftp_config: FTPConfig) -> FTPClient:
        """Create FTP client instance."""
        return FTPClient(ftp_config)

    def test_connect_success(self, client: FTPClient) -> None:
        """Test successful connection."""
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()

            mock_ftp.connect.assert_called_once_with("ftp.example.com", 21)
            mock_ftp.login.assert_called_once_with("testuser", "testpass")
            mock_ftp.cwd.assert_called_once_with("/releases")

    def test_connect_creates_directory(self, client: FTPClient) -> None:
        """Test connection creates directory if needed."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.cwd.side_effect = [ftplib.error_perm("Not found"), None]

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()

            mock_ftp.mkd.assert_called()

    def test_connect_failure(self, client: FTPClient) -> None:
        """Test connection failure raises FTPError."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.connect.side_effect = ftplib.error_temp("Connection failed")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            with pytest.raises(FTPError, match="Failed to connect"):
                client.connect()

    def test_disconnect(self, client: FTPClient) -> None:
        """Test graceful disconnect."""
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            client.disconnect()

            mock_ftp.quit.assert_called_once()

    def test_disconnect_fallback_to_close(self, client: FTPClient) -> None:
        """Test disconnect falls back to close() on quit() failure."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.quit.side_effect = ftplib.error_temp("Quit failed")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            client.disconnect()

            mock_ftp.close.assert_called_once()

    def test_connection_context_manager(self, client: FTPClient) -> None:
        """Test context manager connects and disconnects."""
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            with client.connection():
                mock_ftp.connect.assert_called_once()

            mock_ftp.quit.assert_called_once()

    def test_file_exists_true(self, client: FTPClient) -> None:
        """Test file_exists returns True when file exists."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.size.return_value = 1024

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            result = client.file_exists("test.exe")

            assert result is True
            mock_ftp.size.assert_called_once_with("test.exe")

    def test_file_exists_false(self, client: FTPClient) -> None:
        """Test file_exists returns False when file doesn't exist."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.size.side_effect = ftplib.error_perm("File not found")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            result = client.file_exists("test.exe")

            assert result is False

    def test_file_exists_not_connected(self, client: FTPClient) -> None:
        """Test file_exists raises error when not connected."""
        with pytest.raises(FTPError, match="Not connected"):
            client.file_exists("test.exe")

    def test_delete_file(self, client: FTPClient) -> None:
        """Test file deletion."""
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            client.delete_file("test.exe")

            mock_ftp.delete.assert_called_once_with("test.exe")

    def test_delete_file_failure(self, client: FTPClient) -> None:
        """Test file deletion failure."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.delete.side_effect = ftplib.error_perm("Delete failed")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            with pytest.raises(FTPError, match="Failed to delete"):
                client.delete_file("test.exe")

    def test_rename_file(self, client: FTPClient) -> None:
        """Test file renaming."""
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            client.rename_file("old.exe", "new.exe")

            mock_ftp.rename.assert_called_once_with("old.exe", "new.exe")

    def test_rename_file_failure(self, client: FTPClient) -> None:
        """Test file rename failure."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.rename.side_effect = ftplib.error_perm("Rename failed")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            with pytest.raises(FTPError, match="Failed to rename"):
                client.rename_file("old.exe", "new.exe")

    def test_ensure_directory(self, client: FTPClient) -> None:
        """Test directory creation."""
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            client.ensure_directory("backups")

            mock_ftp.mkd.assert_called_with("backups")

    def test_ensure_directory_exists(self, client: FTPClient) -> None:
        """Test ensure_directory when directory already exists."""
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.mkd.side_effect = ftplib.error_perm("Directory exists")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            client.ensure_directory("backups")  # Should not raise

    def test_upload_file(self, client: FTPClient, tmp_path: Path) -> None:
        """Test file upload."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"test content")

        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            result = client.upload_file(test_file)

            assert result == "test.exe"
            mock_ftp.storbinary.assert_called_once()
            call_args = mock_ftp.storbinary.call_args
            assert call_args[0][0] == "STOR test.exe"

    def test_upload_file_not_connected(self, client: FTPClient, tmp_path: Path) -> None:
        """Test upload raises error when not connected."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"test content")

        with pytest.raises(FTPError, match="Not connected"):
            client.upload_file(test_file)

    def test_upload_file_failure(self, client: FTPClient, tmp_path: Path) -> None:
        """Test upload failure."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"test content")

        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.storbinary.side_effect = ftplib.error_perm("Upload failed")

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.connect()
            with pytest.raises(FTPError, match="Failed to upload"):
                client.upload_file(test_file)
