"""Tests for the full-release orchestration (ReleaseCreator)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.create_config import BatsConfig, CreateConfig
from release_tool.exceptions import ReleaseCreateError
from release_tool.release_creator import ReleaseCreator


def make_config(
    *,
    publish: str | None = "tools/publish.bat",
    english_only: bool = False,
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
        label_format="{version}_{build}",
        english_only=english_only,
        bats=bats,
    )


def ran(mock_run: MagicMock) -> list[list[str]]:
    """Return the command lists passed to the mocked run_command."""
    return [call.args[0] for call in mock_run.call_args_list]


def uses(cmds: list[list[str]], needle: str) -> bool:
    return any(needle in part for cmd in cmds for part in cmd)


def label_capture(mock_capture: MagicMock, version: str = "1.0.0", build: str = "21") -> None:
    """Stub version_get/build_get so the computed label is <version>_<build+1>."""
    mock_capture.side_effect = [version, build]


def prepare_notes(root: Path, label: str = "1.0.0_22") -> None:
    """Create release_notes/<label>/en.json so the notes step is satisfied."""
    notes = root / "release_notes" / label
    notes.mkdir(parents=True)
    (notes / "en.json").write_text("{}")


class TestComputeLabel:
    @patch("release_tool.release_creator.capture_command")
    def test_bare_version(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        assert creator._compute_label() == "1.0.0_22"

    @patch("release_tool.release_creator.capture_command")
    def test_full_label_version(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        """version_get printing a full label is trimmed to the bare version."""
        mock_capture.side_effect = ["1.0.0_21", "21"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        assert creator._compute_label() == "1.0.0_22"

    @patch("release_tool.release_creator.capture_command")
    def test_non_integer_build_raises(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["1.0.0", "not-a-number"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="non-integer build"):
            creator._compute_label()

    @patch("release_tool.release_creator.capture_command")
    def test_empty_version_raises(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["", "21"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="no version"):
            creator._compute_label()


class TestCreateFlow:
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_dry_run_full_sequence(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        assert creator.create(internal=False) is True

        cmds = ran(mock_run)
        assert uses(cmds, "build_increment.bat")
        assert uses(cmds, "translate.bat")
        assert uses(cmds, "build.bat")
        assert uses(cmds, "publish.bat")
        assert uses(cmds, "git")  # commit + tag in dry-run assume publish

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_missing_notes_invokes_codex(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        creator.create(internal=False)
        assert uses(ran(mock_run), "codex")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_internal_skips_notes_and_tags_internal(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        creator.create(internal=True)

        cmds = ran(mock_run)
        assert not uses(cmds, "codex")  # notes skipped
        commit = next(c for c in cmds if c[:2] == ["git", "commit"])
        assert "INTERNAL (app): 1.0.0_22" in commit

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_english_only_skips_translate(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(english_only=True), tmp_path, dry_run=True)
        creator.create(internal=False)
        assert not uses(ran(mock_run), "translate.bat")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_build_failure_rolls_back(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        def fail_on_build(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
            if any(part.endswith("build.bat") for part in cmd):
                raise ReleaseCreateError("build blew up")

        mock_run.side_effect = fail_on_build
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)

        with pytest.raises(ReleaseCreateError, match="build blew up"):
            creator.create(internal=False)

        assert uses(ran(mock_run), "build_decrement.bat")

    @patch("builtins.input", return_value="n")
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_publish_decline_skips_commit(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "publish.bat")
        assert not uses(cmds, "git")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_no_publish_bat_builds_and_stops(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(publish=None), tmp_path, dry_run=True)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "build.bat")
        assert not uses(cmds, "git")  # no publish -> no commit/tag
