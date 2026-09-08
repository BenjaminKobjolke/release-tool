"""Tests for the android and bump-build CLI entry points."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from release_tool.cli import main
from release_tool.cli_android import parse_android_args, parse_bump_build_args
from release_tool.version_file import AppVersion, VersionFile

INI = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /downloads/
remote_filename = tickets.apk
"""


class TestParseAndroidArgs:
    """Tests for `android` argument parsing."""

    def test_defaults(self) -> None:
        """Only the config path is required."""
        args = parse_android_args(["android_release.ini"])

        assert args.config == Path("android_release.ini")
        assert args.project_root is None
        assert args.debug is False
        assert args.dry_run is False
        assert args.verbose is False

    def test_all_flags(self) -> None:
        """Every flag parses."""
        args = parse_android_args(
            ["cfg.ini", "--project-root", "..", "--debug", "--dry-run", "--verbose"]
        )

        assert args.config == Path("cfg.ini")
        assert args.project_root == Path("..")
        assert args.debug is True
        assert args.dry_run is True
        assert args.verbose is True


class TestParseBumpBuildArgs:
    """Tests for `bump-build` argument parsing."""

    def test_defaults_to_increment(self) -> None:
        """Without --decrement the build number goes up."""
        args = parse_bump_build_args(["pubspec.yaml"])

        assert args.version_file == Path("pubspec.yaml")
        assert args.decrement is False

    def test_format_defaults_to_pubspec(self) -> None:
        """Without --format the pubspec syntax is assumed."""
        assert parse_bump_build_args(["pubspec.yaml"]).version_format == "pubspec"

    def test_format_flag(self) -> None:
        """--format selects a Gradle syntax."""
        args = parse_bump_build_args(["build.gradle", "--format", "gradle_groovy"])
        assert args.version_format == "gradle_groovy"

    def test_decrement_flag(self) -> None:
        """--decrement is the rollback direction."""
        assert parse_bump_build_args(["pubspec.yaml", "--decrement"]).decrement is True


class TestMainDispatch:
    """Tests for subcommand dispatch and exit codes."""

    def test_android_dispatches(self, tmp_path: Path) -> None:
        """`android` builds a runner and returns 0 on success."""
        ini = tmp_path / "android_release.ini"
        ini.write_text(INI, encoding="utf-8")

        with patch("release_tool.cli_android.AndroidReleaseRunner") as mock_runner:
            mock_runner.return_value.release.return_value = True
            exit_code = main(["android", str(ini), "--project-root", str(tmp_path), "--dry-run"])

        assert exit_code == 0
        mock_runner.return_value.release.assert_called_once_with(debug=False)

    def test_android_passes_debug(self, tmp_path: Path) -> None:
        """--debug reaches the runner."""
        ini = tmp_path / "android_release.ini"
        ini.write_text(INI, encoding="utf-8")

        with patch("release_tool.cli_android.AndroidReleaseRunner") as mock_runner:
            mock_runner.return_value.release.return_value = True
            main(["android", str(ini), "--project-root", str(tmp_path), "--debug", "--dry-run"])

        mock_runner.return_value.release.assert_called_once_with(debug=True)

    def test_android_missing_config_is_exit_2(self, tmp_path: Path) -> None:
        """A missing INI is a configuration error."""
        assert main(["android", str(tmp_path / "nope.ini")]) == 2

    def test_bump_build_dispatches(self, tmp_path: Path) -> None:
        """`bump-build` bumps the given file and returns 0."""
        version_file = MagicMock(spec=VersionFile)
        version_file.bump.return_value = (
            AppVersion(name="1.0.0", build=2),
            AppVersion(name="1.0.0", build=3),
        )

        with patch("release_tool.cli_android.VersionFile", return_value=version_file):
            exit_code = main(["bump-build", str(tmp_path / "pubspec.yaml")])

        assert exit_code == 0
        version_file.bump.assert_called_once_with(1)

    def test_bump_build_decrement(self, tmp_path: Path) -> None:
        """--decrement passes a negative step."""
        version_file = MagicMock(spec=VersionFile)
        version_file.bump.return_value = (
            AppVersion(name="1.0.0", build=3),
            AppVersion(name="1.0.0", build=2),
        )

        with patch("release_tool.cli_android.VersionFile", return_value=version_file):
            main(["bump-build", str(tmp_path / "pubspec.yaml"), "--decrement"])

        version_file.bump.assert_called_once_with(-1)

    def test_bump_build_missing_file_is_exit_2(self, tmp_path: Path) -> None:
        """A missing pubspec is a configuration error."""
        assert main(["bump-build", str(tmp_path / "pubspec.yaml")]) == 2
