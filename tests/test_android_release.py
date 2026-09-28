"""Tests for the android build-and-upload runner."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from release_tool.android_config import AndroidConfig
from release_tool.android_release import AndroidReleaseRunner
from release_tool.exceptions import FTPError, ReleaseCreateError
from release_tool.ftp_client import FTPClient
from release_tool.release_manager import ReleaseManager
from release_tool.version_file import AppVersion, VersionFile

INI = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /downloads/
remote_filename = tickets.apk
public_url_base = https://example.com/apps
"""

VERSION = AppVersion(name="1.0.0", build=2)
BUMPED = AppVersion(name="1.0.0", build=3)


@pytest.fixture
def config(tmp_path: Path) -> AndroidConfig:
    """An android config with the Flutter defaults."""
    ini = tmp_path / "android_release.ini"
    ini.write_text(INI, encoding="utf-8")
    return AndroidConfig.from_ini_file(ini)


@pytest.fixture
def project_root(tmp_path: Path, config: AndroidConfig) -> Path:
    """A project root with both APKs already present, as after a build."""
    for apk in (config.apk, config.apk_debug):
        path = tmp_path / apk
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"apk")
    return tmp_path


def make_runner(
    config: AndroidConfig,
    project_root: Path,
    dry_run: bool = False,
) -> tuple[AndroidReleaseRunner, MagicMock, MagicMock, MagicMock]:
    """Build a runner with mocked collaborators."""
    manager = MagicMock(spec=ReleaseManager)
    manager.release.return_value = True
    ftp_client = MagicMock(spec=FTPClient)
    version_file = MagicMock(spec=VersionFile)
    version_file.read.return_value = VERSION
    version_file.bump.return_value = (VERSION, BUMPED)
    runner = AndroidReleaseRunner(
        config=config,
        project_root=project_root,
        release_manager=manager,
        ftp_client=ftp_client,
        version_file=version_file,
        dry_run=dry_run,
    )
    return runner, manager, ftp_client, version_file


class TestReleaseBuild:
    """Tests for a release (non-debug) run."""

    def test_bumps_builds_and_uploads(self, config: AndroidConfig, project_root: Path) -> None:
        """The happy path runs every step in order and reports success."""
        runner, manager, ftp_client, version_file = make_runner(config, project_root)
        apk = project_root / config.apk
        calls = MagicMock()
        calls.attach_mock(manager.release, "apk")
        calls.attach_mock(ftp_client.upload_file, "sidecar")

        with patch("release_tool.android_release.run_command") as mock_run:
            # The build is mocked, so re-create the APK the runner just deleted.
            mock_run.side_effect = lambda *a, **k: apk.write_bytes(b"apk")
            assert runner.release(debug=False) is True

        version_file.bump.assert_called_once_with()
        mock_run.assert_called_once_with(config.command, cwd=project_root, dry_run=False)
        manager.release.assert_called_once_with(apk, "tickets.apk")
        sidecar = apk.parent / "tickets.apk.json"
        ftp_client.upload_file.assert_called_once_with(sidecar, "tickets.apk.json")
        assert calls.mock_calls == [
            call.apk(apk, "tickets.apk"),
            call.sidecar(sidecar, "tickets.apk.json"),
        ]
        assert '"version_code": 3' in sidecar.read_text(encoding="utf-8")

    def test_deletes_stale_apk_before_building(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """Verification must not pass on the previous run's artifact."""
        runner, _, _, _ = make_runner(config, project_root)
        apk = project_root / config.apk
        seen: list[bool] = []

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = lambda *a, **k: (
                seen.append(apk.exists()),
                apk.write_bytes(b"apk"),
            )
            runner.release(debug=False)

        assert seen == [False]

    def test_propagates_upload_failure(self, config: AndroidConfig, project_root: Path) -> None:
        """A False from ReleaseManager must not be swallowed into success."""
        runner, manager, ftp_client, _ = make_runner(config, project_root)
        manager.release.return_value = False
        apk = project_root / config.apk

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = lambda *a, **k: apk.write_bytes(b"apk")
            assert runner.release(debug=False) is False

        ftp_client.upload_file.assert_not_called()

    def test_sidecar_failure_says_apk_was_uploaded(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        runner, _, ftp_client, _ = make_runner(config, project_root)
        ftp_client.upload_file.side_effect = FTPError("connection lost")
        apk = project_root / config.apk

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = lambda *a, **k: apk.write_bytes(b"apk")
            with pytest.raises(FTPError, match="APK uploaded, but the version file"):
                runner.release(debug=False)


class TestDebugBuild:
    """Tests for a debug run."""

    def test_uses_debug_variant_and_does_not_bump(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """Debug builds use the debug argv/apk and leave the version alone."""
        runner, manager, ftp_client, version_file = make_runner(config, project_root)
        apk_debug = project_root / config.apk_debug

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = lambda *a, **k: apk_debug.write_bytes(b"apk")
            assert runner.release(debug=True) is True

        version_file.bump.assert_not_called()
        mock_run.assert_called_once_with(config.command_debug, cwd=project_root, dry_run=False)
        manager.release.assert_called_once_with(apk_debug, "tickets-debug.apk")
        ftp_client.upload_file.assert_called_once_with(
            apk_debug.parent / "tickets-debug.apk.json", "tickets-debug.apk.json"
        )

    def test_bump_on_debug_bumps(self, tmp_path: Path, project_root: Path) -> None:
        """With bump_on_debug, a debug build bumps like a release one."""
        ini = tmp_path / "bump_debug.ini"
        ini.write_text(INI + "\n[Build]\nbump_on_debug = true\n", encoding="utf-8")
        config = AndroidConfig.from_ini_file(ini)
        runner, _, _, version_file = make_runner(config, project_root)
        apk_debug = project_root / config.apk_debug

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = lambda *a, **k: apk_debug.write_bytes(b"apk")
            runner.release(debug=True)

        version_file.bump.assert_called_once_with()


class TestRollback:
    """Tests for the bump rollback when the build fails."""

    def test_build_failure_decrements_and_reraises(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """The bump is undone exactly once and the build error still surfaces."""
        runner, _, _, version_file = make_runner(config, project_root)

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = ReleaseCreateError("build blew up")
            with pytest.raises(ReleaseCreateError, match="build blew up"):
                runner.release(debug=False)

        version_file.bump.assert_any_call(-1)
        assert version_file.bump.call_count == 2

    def test_missing_apk_decrements_and_raises(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """A build that "succeeds" without producing the APK is still a failure."""
        runner, manager, _, version_file = make_runner(config, project_root)

        with (
            patch("release_tool.android_release.run_command"),
            pytest.raises(ReleaseCreateError, match="APK not found"),
        ):
            runner.release(debug=False)

        version_file.bump.assert_any_call(-1)
        manager.release.assert_not_called()

    def test_no_rollback_when_nothing_was_bumped(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """A failed debug build has nothing to roll back."""
        runner, _, _, version_file = make_runner(config, project_root)

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = ReleaseCreateError("build blew up")
            with pytest.raises(ReleaseCreateError):
                runner.release(debug=True)

        version_file.bump.assert_not_called()

    def test_failing_rollback_still_reraises_build_error(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """A broken rollback must not mask why the build failed."""
        runner, _, _, version_file = make_runner(config, project_root)
        version_file.bump.side_effect = [(VERSION, BUMPED), OSError("pubspec is locked")]

        with patch("release_tool.android_release.run_command") as mock_run:
            mock_run.side_effect = ReleaseCreateError("build blew up")
            with pytest.raises(ReleaseCreateError, match="build blew up"):
                runner.release(debug=False)


class TestDryRun:
    """Tests for the dry-run contract: nothing written, nothing uploaded."""

    def test_writes_nothing_and_never_uploads(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """Dry run reads the version, narrates the rest, and leaves the APK alone."""
        runner, manager, ftp_client, version_file = make_runner(
            config, project_root, dry_run=True
        )
        apk = project_root / config.apk

        with patch("release_tool.android_release.run_command") as mock_run:
            assert runner.release(debug=False) is True

        version_file.bump.assert_not_called()
        version_file.read.assert_called_once_with()
        mock_run.assert_called_once_with(config.command, cwd=project_root, dry_run=True)
        manager.release.assert_not_called()
        ftp_client.upload_file.assert_not_called()
        assert not (apk.parent / "tickets.apk.json").exists()
        assert apk.exists()

    def test_does_not_fail_when_apk_is_absent(
        self, config: AndroidConfig, project_root: Path
    ) -> None:
        """The APK legitimately does not exist in a dry run."""
        runner, _, _, _ = make_runner(config, project_root, dry_run=True)
        (project_root / config.apk).unlink()

        with patch("release_tool.android_release.run_command"):
            assert runner.release(debug=False) is True
