"""Tests for the full-release orchestration (ReleaseCreator)."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.create_config import BatsConfig, CreateConfig, PublishChannel
from release_tool.exceptions import ReleaseCreateError
from release_tool.github_publisher import GitHubReleaseConfig
from release_tool.release_creator import ReleaseCreator


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


def make_config(
    *,
    publish: str | None = "tools/publish.bat",
    english_only: bool = False,
    versioning: str = "build",
    label_format: str = "{version}_{build}",
    notes_label_format: str = "{version}_{build}",
    build_self_contained: bool = False,
    semver_patch_max: int | None = None,
    publish_channels: list[PublishChannel] | None = None,
    github_release: GitHubReleaseConfig | None = None,
) -> CreateConfig:
    bats = BatsConfig(
        version_get="tools/version_get.bat",
        build_get="tools/build_get.bat",
        build_increment="tools/build_increment.bat",
        build_decrement="tools/build_decrement.bat",
        translate="tools/translate.bat",
        build="tools/build.bat",
        publish=publish,
    )
    return CreateConfig(
        scope="app",
        publish_platform="Store",
        notes_dir="release_notes",
        en_file="en.json",
        label_format=label_format,
        notes_label_format=notes_label_format,
        versioning=versioning,
        previous_version_file="tools/previous_version.txt",
        english_only=english_only,
        build_self_contained=build_self_contained,
        publish_channels=publish_channels or [],
        bats=bats,
        github_release=github_release,
        semver_patch_max=semver_patch_max,
    )


def ran(mock_run: MagicMock) -> list[list[str]]:
    """Return the command lists passed to the mocked run_command."""
    return [call.args[0] for call in mock_run.call_args_list]


def uses(cmds: list[list[str]], needle: str) -> bool:
    return any(needle in part for cmd in cmds for part in cmd)


def fail_on_build(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
    """run_command side_effect: raise once the build bat itself is invoked."""
    if any(part.endswith("build.bat") for part in cmd):
        raise ReleaseCreateError("build blew up")


def two_publish_channels() -> list[PublishChannel]:
    """A Website + Google Play channel pair, shared by the multi-channel tests."""
    return [
        PublishChannel(name="Website", bat="tools/publish_website.bat"),
        PublishChannel(name="Google Play", bat="tools/publish_play.bat"),
    ]


def label_capture(mock_capture: MagicMock, version: str = "1.0.0", build: str = "21") -> None:
    """Stub version_get/build_get so the computed label is <version>_<build+1>."""
    mock_capture.side_effect = [version, build]


def prepare_notes(root: Path, label: str = "1.0.0_22") -> None:
    """Create release_notes/<label>/en.json so the notes step is satisfied."""
    notes = root / "release_notes" / label
    notes.mkdir(parents=True)
    (notes / "en.json").write_text("{}")


class TestCommitStep:
    """A clean index skips only the commit; tag and pushes still run."""

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    @patch("builtins.input", side_effect=["y", "y"])
    def test_clean_tree_skips_commit_but_tags_and_pushes(
        self,
        mock_input: MagicMock,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_publisher_class: MagicMock,
        mock_has_staged_changes: MagicMock,
        tmp_path: Path,
        caplog,
    ) -> None:
        mock_has_staged_changes.return_value = False
        prepare_notes(tmp_path)
        (tmp_path / "release_notes" / "1.0.0_22" / "en.json").write_text(
            '{"title": "1.0.0_22", "notes": ["First"]}'
        )
        github_config = GitHubReleaseConfig(enabled=True, assets=["app.exe"])
        creator = ReleaseCreator(
            make_config(publish=None, github_release=github_config), tmp_path
        )

        with caplog.at_level(logging.INFO):
            assert creator.create() is True

        commands = ran(mock_run)
        assert ["git", "commit", "-m", "RELEASE (app): 1.0.0_22"] not in commands
        git_commands = [command for command in commands if command[0] == "git"]
        assert git_commands == [
            ["git", "add", "-A"],
            ["git", "tag", "1.0.0_22"],
            ["git", "push"],
            ["git", "push", "origin", "1.0.0_22"],
        ]
        mock_publisher_class.return_value.publish.assert_called_once()
        assert "Nothing to commit for 1.0.0_22; skipping git commit." in caplog.text

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    @patch("builtins.input", return_value="y")
    def test_commit_failure_still_raises(
        self,
        mock_input: MagicMock,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_has_staged_changes: MagicMock,
        tmp_path: Path,
    ) -> None:
        def fail_commit(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
            if cmd[:2] == ["git", "commit"]:
                raise ReleaseCreateError("commit failed")

        mock_run.side_effect = fail_commit
        prepare_notes(tmp_path)

        with pytest.raises(ReleaseCreateError, match="commit failed"):
            ReleaseCreator(make_config(publish=None), tmp_path).create()

        assert mock_has_staged_changes.return_value is True
        assert not any(command[:2] == ["git", "tag"] for command in ran(mock_run))

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    def test_dry_run_does_not_check_staged(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_has_staged_changes: MagicMock,
        tmp_path: Path,
    ) -> None:
        prepare_notes(tmp_path)

        ReleaseCreator(make_config(publish=None), tmp_path, dry_run=True).create()

        mock_has_staged_changes.assert_not_called()
        assert ["git", "commit", "-m", "RELEASE (app): 1.0.0_22"] in ran(mock_run)


class TestComputeLabel:
    @patch("release_tool.release_creator.capture_command")
    def test_bare_version(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        labels = creator._compute_labels()
        assert labels.shipping == "1.0.0_22"
        assert labels.previous == "1.0.0_21"

    @patch("release_tool.release_creator.capture_command")
    def test_full_label_version(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        """version_get printing a full label is trimmed to the bare version."""
        mock_capture.side_effect = ["1.0.0_21", "21"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        assert creator._compute_labels().shipping == "1.0.0_22"

    @patch("release_tool.release_creator.capture_command")
    def test_non_integer_build_raises(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["1.0.0", "not-a-number"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="non-integer build"):
            creator._compute_labels()

    @patch("release_tool.release_creator.capture_command")
    def test_empty_version_raises(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["", "21"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="no version"):
            creator._compute_labels()

    @patch("release_tool.release_creator.capture_command")
    def test_notes_label_defaults_to_shipping(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        """Matching note and tag formats produce the same shipping label."""
        label_capture(mock_capture)
        labels = ReleaseCreator(make_config(), tmp_path, dry_run=True)._compute_labels()
        assert labels.notes == labels.shipping == "1.0.0_22"

    @patch("release_tool.release_creator.capture_command")
    def test_notes_label_decoupled_from_commit_label(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        """notes_label_format keys the notes folder independently of the commit/tag label."""
        mock_capture.side_effect = ["1.0.0", "21"]
        config = make_config(label_format="{version}+{build}", notes_label_format="{build}")
        labels = ReleaseCreator(config, tmp_path, dry_run=True)._compute_labels()
        assert labels.shipping == "1.0.0+22"  # commit/tag label
        assert labels.notes == "22"  # notes-folder key


class TestSemverLabels:
    @patch("release_tool.release_creator.capture_command")
    def test_semver_rolls_patch_to_next_minor(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        mock_capture.side_effect = ["1.7.13"]
        creator = ReleaseCreator(
            make_config(versioning="semver", semver_patch_max=10), tmp_path, dry_run=True
        )

        labels = creator._compute_labels()

        assert labels.previous == "1.7.13"
        assert labels.shipping == "1.8.0"
        assert labels.notes == "1.8.0"

    @patch("release_tool.release_creator.capture_command")
    def test_semver_bumps_last_segment(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["0.1.6"]  # build_get is never read in semver
        creator = ReleaseCreator(make_config(versioning="semver"), tmp_path, dry_run=True)
        labels = creator._compute_labels()
        assert labels.previous == "0.1.6"
        assert labels.shipping == "0.1.7"

    @patch("release_tool.release_creator.capture_command")
    def test_semver_non_numeric_last_segment_raises(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        mock_capture.side_effect = ["0.1.x"]
        creator = ReleaseCreator(make_config(versioning="semver"), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="non-numeric last segment"):
            creator._compute_labels()

    @patch("builtins.input", side_effect=["y", "n"])  # publish yes, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_semver_writes_previous_version_file(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_capture.side_effect = ["0.1.6"]
        prepare_notes(tmp_path, label="0.1.7")

        creator = ReleaseCreator(make_config(versioning="semver"), tmp_path, dry_run=False)
        creator.create(internal=False)

        prev_file = tmp_path / "tools" / "previous_version.txt"
        assert prev_file.read_text(encoding="utf-8").strip() == "0.1.6"
        # publish bat takes no args now — it reads the file itself.
        publish = next(c for c in ran(mock_run) if uses([c], "publish.bat"))
        assert publish == ["cmd", "/c", "call", "tools\\publish.bat"]
