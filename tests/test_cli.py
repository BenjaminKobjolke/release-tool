"""Tests for CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from release_tool.cli import main, parse_args, parse_create_args, run
from release_tool.cli_support import WATCHER_ENV_VAR, confirm
from release_tool.exceptions import FTPError


class TestConfirm:
    @patch("builtins.input", return_value="y")
    def test_watcher_marker_precedes_prompt(
        self, mock_input: MagicMock, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv(WATCHER_ENV_VAR, "1")

        assert confirm("Publish X? [y/N]") is True
        assert capsys.readouterr().out == "::tw-input-line::\n"
        mock_input.assert_called_once_with("Publish X? [y/N]: ")

    @patch("builtins.input", return_value="y")
    def test_no_marker_outside_watcher(self, mock_input: MagicMock, monkeypatch, capsys) -> None:
        monkeypatch.delenv(WATCHER_ENV_VAR, raising=False)

        assert confirm("Publish X? [y/N]") is True
        assert capsys.readouterr().out == ""
        mock_input.assert_called_once_with("Publish X? [y/N]: ")

    @patch("builtins.input", return_value="y")
    def test_no_marker_for_other_env_value(
        self, mock_input: MagicMock, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv(WATCHER_ENV_VAR, "0")

        assert confirm("Publish X? [y/N]") is True
        assert capsys.readouterr().out == ""

    @patch("builtins.input", side_effect=[" Y ", "n", ""])
    def test_only_y_confirms(self, mock_input: MagicMock) -> None:
        assert confirm("Continue? [y/N]") is True
        assert confirm("Continue? [y/N]") is False
        assert confirm("Continue? [y/N]") is False


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
        args = parse_args(
            [
                "app.zip",
                "release.ini",
                "--previous-version",
                "1.2.3",
                "--dry-run",
                "--verbose",
            ]
        )

        assert args.file == Path("app.zip")
        assert args.config == Path("release.ini")
        assert args.version == "1.2.3"
        assert args.dry_run is True
        assert args.verbose is True

    def test_parse_previous_version_short_flag(self) -> None:
        """Test parsing previous-version with short flag."""
        args = parse_args(["test.exe", "config.ini", "-p", "2.0.0"])

        assert args.version == "2.0.0"


class TestParseCreateArgs:
    """Tests for `create` subcommand argument parsing."""

    def test_project_root_defaults_none(self) -> None:
        """Without --project-root the flag is None (run_create falls back to cwd)."""
        args = parse_create_args(["cfg.ini"])

        assert args.config == Path("cfg.ini")
        assert args.project_root is None

    def test_project_root_flag(self) -> None:
        """--project-root wires through as a Path."""
        args = parse_create_args(["cfg.ini", "--project-root", "X"])

        assert args.project_root == Path("X")


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
