"""Tests for FTP connection setup and retry behavior."""

import ftplib
from unittest.mock import MagicMock, patch

import pytest

from release_tool.config import FTPConfig
from release_tool.exceptions import FTPError
from release_tool.ftp_client import FTPClient

RealFTP = ftplib.FTP


class TestFTPClientConnection:
    """Tests for FTP connection setup."""

    @pytest.fixture
    def client(self, ftp_config: FTPConfig) -> FTPClient:
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

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            pytest.raises(FTPError, match="Failed to connect"),
        ):
            client.connect()

    def test_connect_retries_when_connection_limit_reached(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.login.side_effect = [
            ftplib.error_perm(
                "530 Sorry, the maximum number of connections (10) for your host "
                "are already connected."
            ),
            None,
        ]

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            patch("release_tool.ftp_client.time.sleep") as mock_sleep,
        ):
            client.connect()

        assert mock_ftp.login.call_count == 2
        mock_sleep.assert_called_once_with(30)
        mock_ftp.quit.assert_called_once()

    def test_connect_retries_on_421_at_greeting(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.connect.side_effect = [ftplib.error_temp("421 Too many connections"), None]

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            patch("release_tool.ftp_client.time.sleep") as mock_sleep,
        ):
            client.connect()

        assert mock_ftp.connect.call_count == 2
        mock_sleep.assert_called_once_with(30)
        mock_ftp.quit.assert_called_once()

    def test_connect_fails_after_persistent_connection_limit(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        error = ftplib.error_perm(
            "530 Sorry, the maximum number of connections (10) for your host "
            "are already connected."
        )
        mock_ftp.login.side_effect = error

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            patch("release_tool.ftp_client.time.sleep") as mock_sleep,
            pytest.raises(
                FTPError,
                match="still reached after 6 attempts.*maximum number of connections",
            ),
        ):
            client.connect()

        assert mock_ftp.login.call_count == 6
        assert mock_sleep.call_count == 5
        assert mock_ftp.quit.call_count == 6

    def test_connect_login_incorrect_fails_immediately(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.login.side_effect = ftplib.error_perm("530 Login incorrect.")

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            patch("release_tool.ftp_client.time.sleep") as mock_sleep,
            pytest.raises(FTPError, match="Failed to connect.*530 Login incorrect"),
        ):
            client.connect()

        mock_ftp.login.assert_called_once_with("testuser", "testpass")
        mock_sleep.assert_not_called()
        mock_ftp.quit.assert_called_once()

    def test_probe_connects_with_timeout_and_closes(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)

        with patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp):
            client.probe(timeout=4.5)

        mock_ftp.connect.assert_called_once_with("ftp.example.com", 21, timeout=4.5)
        mock_ftp.login.assert_called_once_with("testuser", "testpass")
        mock_ftp.cwd.assert_called_once_with("/releases")
        mock_ftp.quit.assert_called_once()

    def test_probe_missing_remote_path_does_not_create_it(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.cwd.side_effect = ftplib.error_perm("550 missing")

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            pytest.raises(FTPError, match="Remote path not found: /releases"),
        ):
            client.probe(timeout=1)

        mock_ftp.mkd.assert_not_called()
        mock_ftp.quit.assert_called_once()

    def test_probe_login_error_is_wrapped_and_closed(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.login.side_effect = ftplib.error_perm("530 Login incorrect")

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            pytest.raises(FTPError, match="Failed to connect"),
        ):
            client.probe(timeout=1)

        mock_ftp.quit.assert_called_once()

    def test_probe_oserror_is_wrapped_and_closed(self, client: FTPClient) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.connect.side_effect = OSError("unreachable")

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            pytest.raises(FTPError, match="Failed to connect"),
        ):
            client.probe(timeout=1)

        mock_ftp.quit.assert_called_once()

    def test_probe_falls_back_to_socket_close_when_quit_fails(
        self, client: FTPClient
    ) -> None:
        mock_ftp = MagicMock(spec=RealFTP)
        mock_ftp.connect.side_effect = OSError("unreachable")
        mock_ftp.quit.side_effect = AttributeError("no socket")

        with (
            patch("release_tool.ftp_client.ftplib.FTP", return_value=mock_ftp),
            pytest.raises(FTPError, match="Failed to connect"),
        ):
            client.probe(timeout=1)

        mock_ftp.close.assert_called_once()

