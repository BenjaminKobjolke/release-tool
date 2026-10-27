"""Tests for keeping release labels and version names in sync."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from test_release_creator import (
    make_config,
    prepare_notes,
    ran,
    uses,
)

from release_tool.create_config import CreateConfig
from release_tool.exceptions import ConfigurationError, ReleaseCreateError
from release_tool.github_publisher import GitHubReleaseConfig
from release_tool.release_creator import ReleaseCreator
from release_tool.release_labels import VersionNameBump
from release_tool.version_file import VersionFile


@pytest.fixture(autouse=True)
def mock_has_staged_changes():
    with patch("release_tool.release_creator.has_staged_changes", return_value=True) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_ensure_free_label():
    with patch(
        "release_tool.release_creator.ensure_free_label",
        side_effect=lambda label, *_a, **_kw: label,
        create=True,
    ) as mock:
        yield mock


class TestVersionNameBump:
    """A full release keeps its label and pubspec version in sync."""

    @staticmethod
    def version_file(root: Path, version: str = "1.1.0+1359") -> VersionFile:
        path = root / "pubspec.yaml"
        path.write_bytes(f"name: app\r\n  version: {version}\r\n\r\nother: x\r\n".encode())
        return VersionFile(path)

    @staticmethod
    def config(notes_format: str = "{build}", publish: str | None = None) -> CreateConfig:
        return make_config(
            publish=publish,
            label_format="{version}+{build}",
            notes_label_format=notes_format,
        )

    @staticmethod
    def bats(version_file: VersionFile, fail_on: str | None = None):
        def run(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
            if dry_run:
                return
            if fail_on and uses([cmd], fail_on):
                raise ReleaseCreateError(f"{fail_on} failed")
            if uses([cmd], "build_increment.bat"):
                version_file.bump()
            if uses([cmd], "build_decrement.bat"):
                version_file.bump(-1)

        return run

    @patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"])
    def test_labels_and_notes(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        creator = ReleaseCreator(
            self.config("{version}_{build}"), tmp_path, version_file=version_file
        )
        labels = creator._compute_labels()
        assert (labels.previous, labels.shipping, labels.notes) == (
            "1.1.0+1359",
            "1.1.1+1360",
            "1.1.1_1360",
        )
        assert labels.name_bump == VersionNameBump("1.1.0", "1.1.1")

    @patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"])
    def test_option_off_keeps_name(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        labels = ReleaseCreator(self.config(), tmp_path)._compute_labels()
        assert labels.shipping == "1.1.0+1360"
        assert labels.name_bump is None
        assert version_file.read().label == "1.1.0+1359"

    @pytest.mark.parametrize(
        ("internal", "keep", "expected"),
        [(False, False, "1.1.1+1360"), (True, False, "1.1.0+1360"), (False, True, "1.1.0+1360")],
    )
    def test_success_and_exceptions(
        self, tmp_path: Path, internal: bool, keep: bool, expected: str
    ) -> None:
        version_file = self.version_file(tmp_path)
        if not internal:
            prepare_notes(tmp_path, "1360")
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command", side_effect=self.bats(version_file)
            ) as run,
            patch("release_tool.release_creator.confirm", return_value=True) as confirm,
        ):
            creator = ReleaseCreator(
                self.config("{build}", "tools/publish.bat"), tmp_path, version_file=version_file
            )
            creator.create(internal=internal, keep_version_name=keep)
        assert version_file.read().label == expected
        assert (tmp_path / "tools/previous_version.txt").read_text().strip() == "1.1.0+1359"
        assert ["git", "tag", expected] in ran(run)
        assert ["git", "push", "origin", expected] in ran(run)
        assert f"Publish {expected} to Store? [y/N]" in [c.args[0] for c in confirm.call_args_list]

    def test_github_release_uses_bumped_tag(self, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        prepare_notes(tmp_path, "1360")
        gh_config = GitHubReleaseConfig(enabled=True, assets=["app.exe"], tag_format="v{label}")
        config = self.config()
        config.github_release = gh_config
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch("release_tool.release_creator.run_command", side_effect=self.bats(version_file)),
            patch("release_tool.release_creator.confirm", return_value=True),
            patch("release_tool.release_creator.GitHubPublisher") as publisher,
            patch("release_tool.release_creator.render_notes_markdown", return_value="notes"),
        ):
            ReleaseCreator(config, tmp_path, version_file=version_file).create()
        assert publisher.return_value.publish.call_args.args[0] == "v1.1.1+1360"

    def test_github_release_formats_asset_paths(self, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        prepare_notes(tmp_path, "1360")
        gh_config = GitHubReleaseConfig(enabled=True, assets=["out/app-{label}.xpi"])
        config = self.config()
        config.github_release = gh_config
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch("release_tool.release_creator.run_command", side_effect=self.bats(version_file)),
            patch("release_tool.release_creator.confirm", return_value=True),
            patch("release_tool.release_creator.GitHubPublisher") as publisher,
            patch("release_tool.release_creator.render_notes_markdown", return_value="notes"),
        ):
            ReleaseCreator(config, tmp_path, version_file=version_file).create()
        assets = publisher.return_value.publish.call_args.args[1]
        assert assets == [tmp_path / "out/app-1.1.1+1360.xpi"]

    @pytest.mark.parametrize("failed", ["translate.bat", "build.bat"])
    def test_failed_build_restores_bytes(self, tmp_path: Path, failed: str) -> None:
        version_file = self.version_file(tmp_path)
        original = version_file.path.read_bytes()
        prepare_notes(tmp_path, "1360")
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command",
                side_effect=self.bats(version_file, failed),
            ),
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(ReleaseCreateError, match="failed"):
                creator.create()
        assert version_file.path.read_bytes() == original

    def test_dry_run_keeps_bytes_and_reports_bumped_label(self, tmp_path: Path, caplog) -> None:
        version_file = self.version_file(tmp_path)
        original = version_file.path.read_bytes()
        prepare_notes(tmp_path, "1360")
        with (
            caplog.at_level(logging.INFO),
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch("release_tool.release_creator.run_command") as run,
        ):
            ReleaseCreator(
                self.config(), tmp_path, dry_run=True, version_file=version_file
            ).create()
        assert version_file.path.read_bytes() == original
        assert "Next release label: 1.1.1+1360" in caplog.text
        assert "[DRY RUN] Would set the version name" in caplog.text
        assert ["git", "tag", "1.1.1+1360"] in ran(run)

    @pytest.mark.parametrize(
        ("file_version", "get_version", "get_build", "error"),
        [
            ("1.1.0+1359", "1.1.0-beta", "1359", "non-numeric"),
            ("1.2.0+1359", "1.1.0", "1359", "1.2.0"),
            ("1.1.0+1358", "1.1.0", "1359", "1358"),
        ],
    )
    def test_mismatch_aborts_before_mutation(
        self, tmp_path: Path, file_version: str, get_version: str, get_build: str, error: str
    ) -> None:
        version_file = self.version_file(tmp_path, file_version)
        original = version_file.path.read_bytes()
        with (
            patch(
                "release_tool.release_creator.capture_command", side_effect=[get_version, get_build]
            ),
            patch("release_tool.release_creator.run_command") as run,
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(ReleaseCreateError, match=error):
                creator.create()
        run.assert_not_called()
        assert version_file.path.read_bytes() == original

    # PermissionError is what the real file write raises; it is not a ReleaseToolError.
    @pytest.mark.parametrize("error", [ConfigurationError, PermissionError])
    def test_failed_name_write_still_decrements_build(
        self, tmp_path: Path, error: type[Exception]
    ) -> None:
        version_file = self.version_file(tmp_path)
        original = version_file.path.read_bytes()
        prepare_notes(tmp_path, "1360")
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command", side_effect=self.bats(version_file)
            ) as run,
            patch.object(version_file, "set_name", side_effect=error("name write failed")),
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(error, match="name write failed"):
                creator.create()
        assert uses(ran(run), "build_decrement.bat")
        assert version_file.path.read_bytes() == original

    def test_failed_name_restore_still_decrements_build(self, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        prepare_notes(tmp_path, "1360")
        write_name = version_file.set_name

        def set_name(name: str) -> object:
            if name == "1.1.0":
                raise OSError("restore failed")
            return write_name(name)

        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command",
                side_effect=self.bats(version_file, "build.bat"),
            ) as run,
            patch.object(version_file, "set_name", side_effect=set_name),
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(ReleaseCreateError, match="build.bat failed"):
                creator.create()
        assert uses(ran(run), "build_decrement.bat")
        assert version_file.read().label == "1.1.1+1359"
