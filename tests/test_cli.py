"""Tests for CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.cli import main, parse_args, run
from release_tool.exceptions import ConfigurationError, FTPError


class TestParseArgs:
    """Tests for argument parsing."""

    def test_parse_minimal_args(self) -> None:
        """Test parsing minimal required arguments."""
        args = parse_args(["test.exe", "config.ini"])

        assert args.file == Path("test.exe")
        assert args.config == Path("config.ini")
        assert args.version is None
        assert args.dry_run is False
        assert args.verbose is False

    def test_parse_all_args(self) -> None:
        """Test parsing all arguments."""
        args = parse_args([
            "app.zip",
            "release.ini",
            "--version", "1.2.3",
            "--dry-run",
            "--verbose",
        ])

        assert args.file == Path("app.zip")
        assert args.config == Path("release.ini")
        assert args.version == "1.2.3"
        assert args.dry_run is True
        assert args.verbose is True

    def test_parse_version_short_flag(self) -> None:
        """Test parsing version with short flag."""
        args = parse_args(["test.exe", "config.ini", "-v", "2.0.0"])

        assert args.version == "2.0.0"


class TestRun:
    """Tests for run function."""

    def test_run_success(self, tmp_path: Path) -> None:
        """Test successful run returns 0."""
        config_path = tmp_path / "config.ini"
        config_path.write_text("""[FTP]
host = ftp.example.com
username = user
password = pass
""")
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        args = parse_args([str(test_file), str(config_path), "--dry-run"])

        result = run(args)

        assert result == 0

    def test_run_configuration_error(self, tmp_path: Path) -> None:
        """Test configuration error returns 2."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")
        config_path = tmp_path / "nonexistent.ini"

        args = parse_args([str(test_file), str(config_path)])

        result = run(args)

        assert result == 2

    def test_run_ftp_error(self, tmp_path: Path) -> None:
        """Test FTP error returns 3."""
        config_path = tmp_path / "config.ini"
        config_path.write_text("""[FTP]
host = ftp.example.com
username = user
password = pass
""")
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        args = parse_args([str(test_file), str(config_path)])

        with patch("release_tool.cli.ReleaseManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.release.side_effect = FTPError("Connection failed")

            result = run(args)

        assert result == 3

    def test_run_file_not_found(self, tmp_path: Path) -> None:
        """Test release failure returns 1."""
        config_path = tmp_path / "config.ini"
        config_path.write_text("""[FTP]
host = ftp.example.com
username = user
password = pass
""")
        nonexistent = tmp_path / "nonexistent.exe"

        args = parse_args([str(nonexistent), str(config_path)])

        result = run(args)

        assert result == 1


class TestMain:
    """Tests for main function."""

    def test_main_success(self, tmp_path: Path) -> None:
        """Test main returns 0 on success."""
        config_path = tmp_path / "config.ini"
        config_path.write_text("""[FTP]
host = ftp.example.com
username = user
password = pass
""")
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        result = main([str(test_file), str(config_path), "--dry-run"])

        assert result == 0

    def test_main_keyboard_interrupt(self, tmp_path: Path) -> None:
        """Test main handles keyboard interrupt."""
        config_path = tmp_path / "config.ini"
        config_path.write_text("""[FTP]
host = ftp.example.com
username = user
password = pass
""")
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"content")

        with patch("release_tool.cli.ReleaseManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.release.side_effect = KeyboardInterrupt()

            result = main([str(test_file), str(config_path)])

        assert result == 130
