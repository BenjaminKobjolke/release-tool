"""Tests for recovering GitHub release publishing after network failures."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from test_github_publisher import fail_result, make_asset, ok_result

from release_tool.exceptions import GitHubReleaseError
from release_tool.github_publisher import (
    GitHubPublisher,
    GitHubReleaseConfig,
    _is_network_error,
)

NETWORK_ERROR = (
    'Patch "https://api.github.com/repos/owner/name/releases/123": read tcp '
    "1.2.3.4:5->6.7.8.9:443: wsarecv: A connection attempt failed ..."
)


class TestGitHubPublisherRetry:
    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_missing_release_retries_create_once(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [
            fail_result(NETWORK_ERROR),
            fail_result("release not found"),
            ok_result(),
        ]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        publisher.publish("v1.0.0", [asset])

        assert mock_run.call_count == 3
        assert [call.args[0][2] for call in mock_run.call_args_list] == [
            "create",
            "view",
            "create",
        ]

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_published_release_uploads_assets_without_edit(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [fail_result(NETWORK_ERROR), ok_result("false\n"), ok_result()]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        publisher.publish("v1.0.0", [asset])

        assert [call.args[0][2] for call in mock_run.call_args_list] == ["create", "view", "upload"]
        assert "--clobber" in mock_run.call_args_list[2].args[0]

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_draft_release_uploads_assets_then_publishes(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [
            fail_result(NETWORK_ERROR),
            ok_result("true\n"),
            ok_result(),
            ok_result(),
        ]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        publisher.publish("v1.0.0", [asset])

        assert [call.args[0][2] for call in mock_run.call_args_list] == [
            "create",
            "view",
            "upload",
            "edit",
        ]
        assert mock_run.call_args_list[3].args[0][4:] == ["--draft=false"]

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_non_network_error_is_not_retried(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.return_value = fail_result("HTTP 401: Bad credentials")
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError, match="HTTP 401"):
            publisher.publish("v1.0.0", [asset])

        mock_run.assert_called_once()

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_second_create_failure_has_recovery_command(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [
            fail_result(NETWORK_ERROR),
            fail_result("release not found"),
            fail_result("second network failure"),
        ]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError) as error:
            publisher.publish("v1.0.0", [asset])

        assert mock_run.call_count == 3
        assert "release-tool github-release v1.0.0" in str(error.value)
        assert str(asset) in str(error.value)

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_remote_check_failure_preserves_create_error(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        mock_run.side_effect = [
            fail_result(NETWORK_ERROR),
            fail_result("view request timed out"),
        ]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True))

        with pytest.raises(GitHubReleaseError) as error:
            publisher.publish("v1.0.0", [asset])

        assert mock_run.call_count == 2
        assert "wsarecv" in str(error.value)
        assert "view request timed out" not in str(error.value)

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            ("HTTP 502: Bad Gateway", True),
            ("request timed out", True),
            ("connection reset by peer", True),
            ("HTTP 401: Bad credentials", False),
            ("HTTP 422: Validation failed", False),
            ("asset missing", False),
        ],
    )
    def test_network_error_classifier(self, stderr: str, expected: bool) -> None:
        assert _is_network_error(stderr) is expected

    @patch("release_tool.github_publisher.subprocess.run")
    @patch("release_tool.github_publisher.shutil.which", return_value="/usr/bin/gh")
    def test_recovery_hint_carries_publish_arguments_and_cwd(
        self, mock_which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        asset = make_asset(tmp_path)
        notes_json = tmp_path / "en.json"
        notes_json.write_text('{"title": "v1.0.0", "notes": []}', encoding="utf-8")
        mock_run.side_effect = [
            fail_result(NETWORK_ERROR),
            fail_result("release not found"),
            fail_result("second network failure"),
        ]
        publisher = GitHubPublisher(GitHubReleaseConfig(enabled=True, repo="owner/name"))

        with pytest.raises(GitHubReleaseError) as error:
            publisher.publish(
                "v1.0.0",
                [asset],
                title="Release title",
                notes_json=notes_json,
                cwd=tmp_path,
            )

        message = str(error.value)
        assert "--repo owner/name" in message
        assert "--title" in message and "Release title" in message
        assert f"--notes-json {notes_json}" in message
        assert f"run from {tmp_path}" in message
