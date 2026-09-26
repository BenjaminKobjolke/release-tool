"""Integration test: `release-tool android --dry-run` end-to-end.

Exercises the real CLI dispatch + config load + variant resolution against a
throwaway Flutter-shaped project. Needs no platform skip: a dry run never
spawns the build command and never opens an FTP connection.
"""

from pathlib import Path

import pytest

from release_tool import config as config_module
from release_tool.cli import main

PUBSPEC = "name: demo\r\nversion: 1.0.0+2\r\n\r\nenvironment:\r\n"

CONFIG = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /downloads/
remote_filename = demo.apk
public_url_base = https://example.com/apps

[OldFileHandling]
policy = delete

[Build]
command = fvm flutter build apk --release --no-shrink
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway project with a CRLF pubspec and an android config."""
    (tmp_path / "pubspec.yaml").write_bytes(PUBSPEC.encode("utf-8"))
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "android_release.ini").write_text(CONFIG, encoding="utf-8")
    return tmp_path


def test_dry_run_succeeds_and_changes_nothing(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A dry run resolves everything, writes nothing, and uploads nothing."""
    pubspec = project / "pubspec.yaml"
    before = pubspec.read_bytes()

    with caplog.at_level("INFO"):
        exit_code = main(
            [
                "android",
                str(project / "tools" / "android_release.ini"),
                "--project-root",
                str(project),
                "--dry-run",
            ]
        )

    assert exit_code == 0
    assert pubspec.read_bytes() == before

    log = caplog.text
    assert "fvm flutter build apk --release --no-shrink" in log
    assert "1.0.0+2" in log
    assert "https://example.com/apps/demo.apk" in log


def test_dry_run_resolves_ftp_profile(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The CLI resolves profiles through the shared config boundary."""
    profiles = tmp_path / "ftp_profiles.ini"
    profiles.write_text(
        """[apps]
host = profile.example.com
username = deploy
password = secret
remote_path = /downloads/
public_url_base = https://example.com/apps
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "PROFILES_FILE", profiles)
    (project / "tools" / "android_release.ini").write_text(
        """[FTP]
profile = apps
remote_filename = demo.apk
""",
        encoding="utf-8",
    )

    with caplog.at_level("INFO"):
        exit_code = main(
            [
                "android",
                str(project / "tools" / "android_release.ini"),
                "--project-root",
                str(project),
                "--dry-run",
            ]
        )

    assert exit_code == 0
    assert "profile.example.com:21/downloads/demo.apk" in caplog.text


def test_dry_run_debug_uses_debug_name(project: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The debug variant reports the -debug remote name."""
    with caplog.at_level("INFO"):
        exit_code = main(
            [
                "android",
                str(project / "tools" / "android_release.ini"),
                "--project-root",
                str(project),
                "--debug",
                "--dry-run",
            ]
        )

    assert exit_code == 0
    assert "https://example.com/apps/demo-debug.apk" in caplog.text


def test_bump_build_round_trip_preserves_bytes(project: Path) -> None:
    """bump-build then --decrement restores the CRLF pubspec exactly."""
    pubspec = project / "pubspec.yaml"
    before = pubspec.read_bytes()

    assert main(["bump-build", str(pubspec)]) == 0
    assert b"version: 1.0.0+3" in pubspec.read_bytes()

    assert main(["bump-build", str(pubspec), "--decrement"]) == 0
    assert pubspec.read_bytes() == before


GRADLE_CONFIG = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /downloads/
remote_filename = demo.apk

[Build]
command = cmd /c call tools\build_android.bat release
apk = app/build/outputs/apk/release/app-release.apk
version_file = app/build.gradle
version_file_format = gradle_groovy
"""

GRADLE_BUILD = (
    "android {\r\n"
    "    defaultConfig {\r\n"
    "        versionCode 201\r\n"
    '        versionName "2.1.5"\r\n'
    "    }\r\n"
    "    productFlavors {\r\n"
    "        free {\r\n"
    "            versionCode 201\r\n"
    "        }\r\n"
    "    }\r\n"
    "}\r\n"
)


@pytest.fixture
def gradle_project(tmp_path: Path) -> Path:
    """A throwaway Gradle project with versionCode declared twice, CRLF."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "build.gradle").write_bytes(GRADLE_BUILD.encode("utf-8"))
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "android_release.ini").write_text(GRADLE_CONFIG, encoding="utf-8")
    return tmp_path


def test_gradle_dry_run_resolves_and_changes_nothing(
    gradle_project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A Gradle project dry-runs like a Flutter one and its build file is untouched."""
    build_gradle = gradle_project / "app" / "build.gradle"
    before = build_gradle.read_bytes()

    with caplog.at_level("INFO"):
        exit_code = main(
            [
                "android",
                str(gradle_project / "tools" / "android_release.ini"),
                "--project-root",
                str(gradle_project),
                "--dry-run",
            ]
        )

    assert exit_code == 0
    assert build_gradle.read_bytes() == before
    assert "cmd /c call tools\build_android.bat release" in caplog.text
    # The Gradle formats carry no version name, so the label is the build number.
    assert "Version: 201" in caplog.text


def test_gradle_bump_round_trip_moves_both_occurrences(gradle_project: Path) -> None:
    """bump-build then --decrement restores the CRLF file exactly."""
    build_gradle = gradle_project / "app" / "build.gradle"
    before = build_gradle.read_bytes()

    assert main(["bump-build", str(build_gradle), "--format", "gradle_groovy"]) == 0
    assert build_gradle.read_text(encoding="utf-8").count("versionCode 202") == 2

    assert main(["bump-build", str(build_gradle), "--format", "gradle_groovy", "--decrement"]) == 0
    assert build_gradle.read_bytes() == before
