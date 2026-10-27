"""Tests for release creator behavior."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from test_release_creator import (
    label_capture,
    make_config,
    prepare_notes,
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


class TestGitHubReleaseGate:
    """The GitHub Release gate runs after commit/tag/push, and only if that ran."""

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", return_value="n")  # commit declined
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_no_config_skips_gate(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(publish=None), tmp_path, dry_run=False)
        creator.create(internal=False)

        mock_publisher_class.assert_not_called()

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", return_value="n")  # commit declined -> gate never offered
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_commit_declined_skips_gate(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        gh_config = GitHubReleaseConfig(enabled=True, assets=["target/app.exe"])

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        mock_publisher_class.assert_not_called()

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", side_effect=["y", "n"])  # commit yes, github release no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_github_release_declined(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        gh_config = GitHubReleaseConfig(enabled=True, assets=["target/app.exe"])

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        mock_publisher_class.return_value.publish.assert_not_called()

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", side_effect=["y", "y"])  # commit yes, github release yes
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_github_release_published_after_commit(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        (tmp_path / "release_notes" / "1.0.0_22" / "en.json").write_text(
            '{"title": "1.0.0_22", "notes": ["First"]}'
        )
        gh_config = GitHubReleaseConfig(
            enabled=True, repo="owner/name", assets=["target/app.exe"], tag_format="v{label}"
        )

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        mock_publisher_class.assert_called_once_with(gh_config)
        publish_call = mock_publisher_class.return_value.publish.call_args
        assert publish_call.args[0] == "v1.0.0_22"
        assert publish_call.args[1] == [tmp_path / "target" / "app.exe"]
        assert publish_call.kwargs["cwd"] == tmp_path

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", side_effect=["y", "y"])  # commit yes, github release yes
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_internal_release_skips_notes(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        gh_config = GitHubReleaseConfig(enabled=True, assets=["target/app.exe"])

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=True)

        publish_call = mock_publisher_class.return_value.publish.call_args
        assert publish_call.kwargs["notes"] is None


