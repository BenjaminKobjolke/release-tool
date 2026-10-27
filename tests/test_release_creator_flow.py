"""Tests for release creator behavior."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from test_release_creator import (
    fail_on_build,
    label_capture,
    make_config,
    prepare_notes,
    ran,
    uses,
)

from release_tool.exceptions import ReleaseCreateError
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
        assert uses(cmds, "git")  # commit + tag + push in dry-run assume yes
        assert ["git", "push"] in cmds  # push happens on commit
        assert ["git", "push", "origin", "1.0.0_22"] in cmds

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_missing_notes_invokes_codex(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        creator.create(internal=False)
        codex_call = next(call for call in mock_run.call_args_list if "codex" in call.args[0])
        assert codex_call.kwargs == {"close_stdin": True}
        assert all(
            call.kwargs.get("close_stdin") is not True
            for call in mock_run.call_args_list
            if call is not codex_call
        )

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_notes_lookup_uses_notes_label(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Notes in their own folder satisfy the step; commit uses the full label."""
        mock_capture.side_effect = ["1.0.0", "21"]
        prepare_notes(tmp_path, label="22")  # build-number folder, not the commit label
        config = make_config(label_format="{version}+{build}", notes_label_format="{build}")

        creator = ReleaseCreator(config, tmp_path, dry_run=True)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "codex")  # found at notes label, no authoring
        assert ["git", "push", "origin", "1.0.0+22"] in cmds  # tag uses full label

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
        mock_run.side_effect = fail_on_build
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)

        with pytest.raises(ReleaseCreateError, match="build blew up"):
            creator.create(internal=False)

        assert uses(ran(mock_run), "build_decrement.bat")

    @patch("builtins.input", side_effect=["n", "y"])  # publish no, commit yes
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_publish_declined_still_commits(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Publish and commit are independent — declining publish still commits."""
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "publish.bat")
        assert any(c[:2] == ["git", "commit"] for c in cmds)
        assert ["git", "push"] in cmds

    @patch("builtins.input", side_effect=["y", "n"])  # publish yes, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_commit_declined_still_publishes(
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
        assert uses(cmds, "publish.bat")
        assert not uses(cmds, "git")

    @patch("builtins.input", return_value="n")  # publish n/a, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_no_publish_bat_skips_publish_only(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No publish bat skips only the publish step; commit is still offered."""
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(publish=None), tmp_path, dry_run=False)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "build.bat")
        assert not uses(cmds, "publish")
        assert not uses(cmds, "git")  # commit declined above


class TestBuildSelfContained:
    """A monolithic build bat owns increment/translate/rollback itself."""

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_skips_increment_and_translate(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(build_self_contained=True), tmp_path, dry_run=True)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "build_increment.bat")
        assert not uses(cmds, "translate.bat")
        assert uses(cmds, "build.bat")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_build_failure_does_not_decrement(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        mock_run.side_effect = fail_on_build
        creator = ReleaseCreator(make_config(build_self_contained=True), tmp_path, dry_run=False)

        with pytest.raises(ReleaseCreateError, match="build blew up"):
            creator.create(internal=False)

        assert not uses(ran(mock_run), "build_decrement.bat")


