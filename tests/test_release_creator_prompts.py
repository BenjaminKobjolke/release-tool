"""Tests for release creator behavior."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from test_release_creator import (
    make_config,
    prepare_notes,
    ran,
    two_publish_channels,
    uses,
)

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


class TestAssumeYes:
    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    @patch("builtins.input", side_effect=AssertionError("input called"))
    def test_yes_skips_every_prompt(
        self,
        mock_input: MagicMock,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
        caplog,
    ) -> None:
        caplog.set_level(logging.INFO)
        prepare_notes(tmp_path)
        (tmp_path / "release_notes" / "1.0.0_22" / "en.json").write_text(
            '{"title": "1.0.0_22", "notes": ["First"]}'
        )
        config = make_config(
            publish=None,
            publish_channels=two_publish_channels(),
            github_release=GitHubReleaseConfig(enabled=True, assets=["app.exe"]),
        )

        result = ReleaseCreator(config, tmp_path, assume_yes=True).create()

        assert result is True
        mock_input.assert_not_called()
        cmds = ran(mock_run)
        assert uses(cmds, "publish_website.bat")
        assert uses(cmds, "publish_play.bat")
        assert ["git", "tag", "1.0.0_22"] in cmds
        assert ["git", "push", "origin", "1.0.0_22"] in cmds
        mock_publisher_class.return_value.publish.assert_called_once()
        assert "Auto-confirmed: Publish 1.0.0_22 to Website? [y/N] (--yes)" in caplog.text
        assert "Auto-confirmed: Commit, tag and push 1.0.0_22? [y/N] (--yes)" in caplog.text
        assert "Auto-confirmed: Create GitHub Release" in caplog.text

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    @patch("builtins.input", side_effect=["y", "n", "n"])
    def test_without_yes_still_prompts(
        self,
        mock_input: MagicMock,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        prepare_notes(tmp_path)
        config = make_config(
            publish=None,
            publish_channels=two_publish_channels(),
            github_release=GitHubReleaseConfig(enabled=True, assets=["app.exe"]),
        )

        ReleaseCreator(config, tmp_path).create()

        assert mock_input.call_count == 3

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command", side_effect=["1.0.0", "21"])
    @patch("builtins.input", side_effect=AssertionError("input called"))
    def test_dry_run_with_yes(
        self,
        mock_input: MagicMock,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
        caplog,
    ) -> None:
        caplog.set_level(logging.INFO)
        prepare_notes(tmp_path)

        result = ReleaseCreator(
            make_config(publish=None), tmp_path, dry_run=True, assume_yes=True
        ).create()

        assert result is True
        mock_input.assert_not_called()
        assert "[DRY RUN] Would prompt:" in caplog.text


