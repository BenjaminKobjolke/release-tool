"""Tests for the android command's configuration."""

from pathlib import Path

import pytest

from release_tool.android_config import AndroidConfig
from release_tool.exceptions import ConfigurationError

MINIMAL_INI = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /downloads/
remote_filename = tickets.apk
"""


def write_ini(tmp_path: Path, content: str) -> Path:
    """Write an android config INI and return its path."""
    path = tmp_path / "android_release.ini"
    path.write_text(content, encoding="utf-8")
    return path


class TestFromIniFile:
    """Tests for AndroidConfig.from_ini_file()."""

    def test_defaults(self, tmp_path: Path) -> None:
        """A project following the Flutter conventions needs no [Build] section."""
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, MINIMAL_INI))

        assert config.command == ["fvm", "flutter", "build", "apk", "--release"]
        assert config.command_debug == ["fvm", "flutter", "build", "apk", "--debug"]
        assert config.apk == Path("build/app/outputs/flutter-apk/app-release.apk")
        assert config.apk_debug == Path("build/app/outputs/flutter-apk/app-debug.apk")
        assert config.version_file == Path("pubspec.yaml")
        assert config.bump_on_debug is False

    def test_reuses_release_config(self, tmp_path: Path) -> None:
        """[FTP]/[OldFileHandling] are parsed by the existing ReleaseConfig."""
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, MINIMAL_INI))

        assert config.release.ftp.host == "ftp.example.com"
        assert config.release.ftp.remote_filename == "tickets.apk"

    def test_command_is_shlex_split(self, tmp_path: Path) -> None:
        """turbo-habits' flag set survives, quoted arguments included."""
        content = MINIMAL_INI + (
            "\n[Build]\n"
            "command = fvm flutter build apk --release --target-platform android-arm64 "
            '--no-tree-shake-icons "--dart-define=A B"\n'
        )
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.command == [
            "fvm",
            "flutter",
            "build",
            "apk",
            "--release",
            "--target-platform",
            "android-arm64",
            "--no-tree-shake-icons",
            "--dart-define=A B",
        ]

    def test_command_keeps_windows_backslashes(self, tmp_path: Path) -> None:
        """Backslashes are path separators here, not escapes — this is a Windows tool."""
        content = MINIMAL_INI + (
            "\n[Build]\ncommand = cmd /c call tools\\build_android.bat release\n"
        )
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.command == [
            "cmd",
            "/c",
            "call",
            "tools\\build_android.bat",
            "release",
        ]

    def test_overrides(self, tmp_path: Path) -> None:
        """Every [Build] key can be overridden."""
        content = MINIMAL_INI + (
            "\n[Build]\n"
            "command_debug = flutter build apk --profile\n"
            "apk = out/release.apk\n"
            "apk_debug = out/debug.apk\n"
            "version_file = nested/pubspec.yaml\n"
            "bump_on_debug = true\n"
        )
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.command_debug == ["flutter", "build", "apk", "--profile"]
        assert config.apk == Path("out/release.apk")
        assert config.apk_debug == Path("out/debug.apk")
        assert config.version_file == Path("nested/pubspec.yaml")
        assert config.bump_on_debug is True

    def test_version_file_format_defaults_to_pubspec(self, tmp_path: Path) -> None:
        """Flutter projects need no format key."""
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, MINIMAL_INI))

        assert config.version_file_format == "pubspec"

    def test_version_file_format_override(self, tmp_path: Path) -> None:
        """Gradle projects select their own syntax."""
        content = MINIMAL_INI + (
            "\n[Build]\nversion_file = app/build.gradle.kts\nversion_file_format = gradle_kts\n"
        )
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.version_file == Path("app/build.gradle.kts")
        assert config.version_file_format == "gradle_kts"

    def test_unknown_version_file_format_raises(self, tmp_path: Path) -> None:
        """A typo must name the valid formats rather than failing later at bump time."""
        content = MINIMAL_INI + "\n[Build]\nversion_file_format = gradle\n"

        with pytest.raises(ConfigurationError, match="version_file_format"):
            AndroidConfig.from_ini_file(write_ini(tmp_path, content))

    def test_missing_remote_filename_raises(self, tmp_path: Path) -> None:
        """The android command always renames on upload, so the name is required."""
        content = MINIMAL_INI.replace("remote_filename = tickets.apk\n", "")

        with pytest.raises(ConfigurationError, match="remote_filename"):
            AndroidConfig.from_ini_file(write_ini(tmp_path, content))

    def test_pre_signing_raises(self, tmp_path: Path) -> None:
        """Authenticode signing is meaningless for an APK and would block on the timeout."""
        content = MINIMAL_INI + (
            "\n[PreSigning]\n"
            "enabled = true\n"
            "network_path = //server/sign\n"
            "network_path_signed = //server/sign/signed\n"
            "expected_signer = XIDA GmbH\n"
        )

        with pytest.raises(ConfigurationError, match="PreSigning"):
            AndroidConfig.from_ini_file(write_ini(tmp_path, content))

    def test_invalid_bump_on_debug_raises(self, tmp_path: Path) -> None:
        """A typo'd boolean must fail loudly, not default to false."""
        content = MINIMAL_INI + "\n[Build]\nbump_on_debug = yes please\n"

        with pytest.raises(ConfigurationError, match="bump_on_debug"):
            AndroidConfig.from_ini_file(write_ini(tmp_path, content))


class TestVariant:
    """Tests for AndroidConfig.variant() — everything derives from `debug`."""

    def test_release_variant(self, tmp_path: Path) -> None:
        """The release variant bumps and uploads under the configured name."""
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, MINIMAL_INI))

        variant = config.variant(debug=False)

        assert variant.command == config.command
        assert variant.apk == config.apk
        assert variant.remote_filename == "tickets.apk"
        assert variant.bump is True

    def test_debug_variant(self, tmp_path: Path) -> None:
        """The debug variant does not bump and gets the -debug remote name."""
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, MINIMAL_INI))

        variant = config.variant(debug=True)

        assert variant.command == config.command_debug
        assert variant.apk == config.apk_debug
        assert variant.remote_filename == "tickets-debug.apk"
        assert variant.bump is False

    def test_bump_on_debug_flips_debug_bump(self, tmp_path: Path) -> None:
        """turbo-habits bumps on debug builds too."""
        content = MINIMAL_INI + "\n[Build]\nbump_on_debug = true\n"
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.variant(debug=True).bump is True
        assert config.variant(debug=False).bump is True

    def test_debug_name_without_suffix(self, tmp_path: Path) -> None:
        """A remote name with no extension still gets the suffix appended."""
        content = MINIMAL_INI.replace("tickets.apk", "tickets")
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.variant(debug=True).remote_filename == "tickets-debug"

    def test_public_url_is_derived(self, tmp_path: Path) -> None:
        """The URL follows the remote name, so the two can never drift."""
        content = MINIMAL_INI + "public_url_base = https://example.com/apps\n"
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, content))

        assert config.variant(debug=False).public_url == "https://example.com/apps/tickets.apk"
        assert config.variant(debug=True).public_url == "https://example.com/apps/tickets-debug.apk"

    def test_public_url_none_without_base(self, tmp_path: Path) -> None:
        """The URL is optional; nothing is reported when no base is configured."""
        config = AndroidConfig.from_ini_file(write_ini(tmp_path, MINIMAL_INI))

        assert config.variant(debug=False).public_url is None
