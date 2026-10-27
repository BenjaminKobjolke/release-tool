"""Tests for release creator behavior."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from test_release_creator import (
    label_capture,
    make_config,
    prepare_notes,
    ran,
    two_publish_channels,
    uses,
)

from release_tool.exceptions import ReleaseCreateError
from release_tool.release_creator import ReleaseCreator
from release_tool.tag_guard import TagConflict


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


class TestExistingTag:
    """The shipping label is resolved before notes, bumps, and build work."""

    @pytest.mark.parametrize("dry_run", [False, True])
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    def test_conflict_stops_before_commands_or_notes(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        dry_run: bool,
        mock_ensure_free_label: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ensure_free_label.side_effect = ReleaseCreateError("release tag already exists")
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=dry_run)
        creator._ensure_notes = MagicMock()

        with pytest.raises(ReleaseCreateError, match="already exists"):
            creator.create()

        mock_ensure_free_label.assert_called_once()
        mock_run.assert_not_called()
        assert mock_capture.call_count == 2
        assert not (tmp_path / "release_notes").exists()

    @pytest.mark.parametrize(
        ("dry_run", "self_contained", "bump_if_tagged", "assume_yes", "expected_mode"),
        [
            (False, False, False, False, TagConflict.ASK),
            (False, False, False, True, TagConflict.STOP),
            (True, False, True, False, TagConflict.STOP),
            (False, True, True, False, TagConflict.STOP),
            (False, False, True, True, TagConflict.AUTO),
        ],
    )
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    def test_conflict_mode_is_selected_from_create_options(
        self,
        mock_capture: MagicMock,
        dry_run: bool,
        self_contained: bool,
        bump_if_tagged: bool,
        assume_yes: bool,
        expected_mode: TagConflict,
        mock_ensure_free_label: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ensure_free_label.side_effect = ReleaseCreateError("stop after conflict check")
        creator = ReleaseCreator(
            make_config(build_self_contained=self_contained),
            tmp_path,
            dry_run=dry_run,
            assume_yes=assume_yes,
            bump_if_tagged=bump_if_tagged,
        )

        with pytest.raises(ReleaseCreateError, match="stop after conflict check"):
            creator.create(internal=True)

        assert mock_ensure_free_label.call_args.args[:3] == (
            "1.0.0_22",
            tmp_path,
            expected_mode,
        )

    @patch("release_tool.release_creator.run_command")
    @patch(
        "release_tool.release_creator.capture_command",
        side_effect=["1.0.0", "21", "1.0.0", "22"],
    )
    def test_catch_up_recomputes_shipping_label_before_notes(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_ensure_free_label: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ensure_free_label.side_effect = lambda _label, _cwd, _mode, catch_up: catch_up()
        creator = ReleaseCreator(
            make_config(), tmp_path, bump_if_tagged=True, assume_yes=True
        )
        notes = MagicMock()
        creator._ensure_notes = notes

        creator.create()

        assert uses(ran(mock_run), "build_increment.bat")
        notes.assert_called_once_with("1.0.0_23")
        assert mock_capture.call_count == 4

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    def test_internal_release_also_checks_its_shipping_label(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_ensure_free_label: MagicMock,
        tmp_path: Path,
    ) -> None:
        creator = ReleaseCreator(make_config(), tmp_path, assume_yes=True)

        creator.create(internal=True)

        mock_ensure_free_label.assert_called_once()
        assert mock_ensure_free_label.call_args.args[0] == "1.0.0_22"


class TestMultiChannelPublish:
    """Each publish channel is gated independently."""

    @patch("builtins.input", side_effect=["y", "n", "n"])  # website yes, play no, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_each_channel_gated_independently(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        channels = two_publish_channels()

        creator = ReleaseCreator(
            make_config(publish=None, publish_channels=channels), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "publish_website.bat")
        assert not uses(cmds, "publish_play.bat")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_dry_run_runs_every_channel(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        channels = two_publish_channels()

        creator = ReleaseCreator(
            make_config(publish=None, publish_channels=channels), tmp_path, dry_run=True
        )
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "publish_website.bat")
        assert uses(cmds, "publish_play.bat")


