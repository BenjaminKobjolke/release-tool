"""Tests for GitHub Releases publishing (GitHubPublisher / render_notes_markdown)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.exceptions import GitHubReleaseError
from release_tool.github_publisher import (
    GitHubPublisher,
    GitHubReleaseConfig,
    render_notes_markdown,
)


def make_asset(tmp_path: Path, name: str = "app.exe") -> Path:
    asset = tmp_path / name
    asset.write_bytes(b"content")
    return asset


def ok_result(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


def fail_result(stderr: str) -> MagicMock:
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = stderr
    return result


class TestRenderNotesMarkdown:
    def test_renders_title_and_notes(self, tmp_path: Path) -> None:
        en_json = tmp_path / "en.json"
        en_json.write_text(json.dumps({"title": "1.7.5", "notes": ["First", "Second"]}))

        markdown = render_notes_markdown(en_json)

        assert markdown == "# 1.7.5\n\n- First\n- Second\n"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GitHubReleaseError, match="not found"):
            render_notes_markdown(tmp_path / "missing.json")

    def test_bad_json_raises(self, tmp_path: Path) -> None:
        en_json = tmp_path / "en.json"
        en_json.write_text("{not json")

        with pytest.raises(GitHubReleaseError):
            render_notes_markdown(en_json)

    def test_wrong_shape_raises(self, tmp_path: Path) -> None:
        en_json = tmp_path / "en.json"
        en_json.write_text(json.dumps({"title": "1.7.5"}))  # missing 'notes'

        with pytest.raises(GitHubReleaseError, match="title.*notes"):
            render_notes_markdown(en_json)


class TestPublish:
    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_dry_run_builds_argv_without_running(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True, repo="owner/name"))

        publisher.publish("v1.0.0", [asset], notes="body", dry_run=True)

        mock_run.assert_not_called()

    @patch("release_tool.github_publisher.shutil.which", return_value=None)
    def test_missing_gh_raises(self, mock_which: MagicMock, tmp_path: Path) -> None:
        asset = make_asset(tmp_path)
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError, match="gh CLI not found"):
            publisher.publish("v1.0.0", [asset])

    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_missing_asset_raises(self, mock_which: MagicMock, tmp_path: Path) -> None:
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError, match="Asset not found"):
            publisher.publish("v1.0.0", [tmp_path / "missing.exe"])

    @patch("release_tool.github_publisher.subprocess.run", return_value=ok_result())
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_success_runs_create(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True, repo="owner/name"))

        publisher.publish("v1.0.0", [asset], title="v1.0.0")

        argv = mock_run.call_args.args[0]
        assert argv[:4] == ["gh", "release", "create", "v1.0.0"]
        assert str(asset) in argv
        assert "--repo" in argv and "owner/name" in argv
        assert "--generate-notes" in argv  # no notes given

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_non_zero_exit_raises(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.return_value = fail_result("some other gh error")
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError, match="some other gh error"):
            publisher.publish("v1.0.0", [asset])

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_already_exists_falls_back_to_upload(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [fail_result("release v1.0.0 already exists"), ok_result()]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True, repo="owner/name"))

        publisher.publish("v1.0.0", [asset])

        assert mock_run.call_count == 2
        upload_argv = mock_run.call_args_list[1].args[0]
        assert upload_argv[:4] == ["gh", "release", "upload", "v1.0.0"]
        assert "--clobber" in upload_argv

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_upload_fallback_failure_raises(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [
            fail_result("release v1.0.0 already exists"),
            fail_result("upload blew up"),
        ]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError, match="upload blew up"):
            publisher.publish("v1.0.0", [asset])

    @patch("release_tool.github_publisher.subprocess.run", return_value=ok_result())
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_notes_written_to_temp_file_and_cleaned_up(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        publisher.publish("v1.0.0", [asset], notes="# Title\n\n- item")

        argv = mock_run.call_args.args[0]
        notes_file = Path(argv[argv.index("--notes-file") + 1])
        assert not notes_file.exists()  # cleaned up after the call
