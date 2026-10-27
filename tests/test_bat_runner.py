"""Focused tests for external command execution."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.bat_runner import find_existing_tag, has_staged_changes, run_command
from release_tool.exceptions import ReleaseCreateError


@patch("release_tool.bat_runner.subprocess.run")
def test_run_command_inherits_stdin(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.return_value.returncode = 0

    run_command(["tool"], tmp_path)

    mock_run.assert_called_once_with(["tool"], cwd=tmp_path, stdin=None)


@patch("release_tool.bat_runner.subprocess.run")
def test_run_command_can_close_stdin(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.return_value.returncode = 0

    run_command(["tool"], tmp_path, close_stdin=True)

    mock_run.assert_called_once_with(["tool"], cwd=tmp_path, stdin=subprocess.DEVNULL)


@patch("release_tool.bat_runner.subprocess.run")
def test_has_staged_changes_returns_false_when_index_is_clean(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value.returncode = 0

    assert has_staged_changes(tmp_path) is False

    argv = mock_run.call_args.args[0]
    assert argv[-3:] == ["diff", "--cached", "--quiet"]
    assert mock_run.call_args.kwargs["cwd"] == tmp_path


@patch("release_tool.bat_runner.subprocess.run")
def test_has_staged_changes_returns_true_when_index_has_changes(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value.returncode = 1

    assert has_staged_changes(tmp_path) is True


@patch("release_tool.bat_runner.subprocess.run")
def test_has_staged_changes_raises_for_other_git_errors(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value.returncode = 128

    with pytest.raises(ReleaseCreateError, match="exit 128"):
        has_staged_changes(tmp_path)


@patch("release_tool.bat_runner.subprocess.run")
def test_has_staged_changes_wraps_process_start_errors(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.side_effect = OSError("missing git")

    with pytest.raises(ReleaseCreateError, match="Failed to start"):
        has_staged_changes(tmp_path)


@patch("release_tool.bat_runner.subprocess.run")
def test_find_existing_tag_returns_local_hit_without_checking_origin(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value.returncode = 0

    assert find_existing_tag("1.2.3", tmp_path) == "locally"

    command = mock_run.call_args.args[0]
    assert command[0].lower().endswith(("git", "git.exe"))
    assert command[1:] == ["rev-parse", "-q", "--verify", "refs/tags/1.2.3"]
    assert mock_run.call_args.kwargs == {
        "cwd": tmp_path,
        "capture_output": True,
        "text": True,
    }


@patch("release_tool.bat_runner.subprocess.run")
def test_find_existing_tag_returns_origin_hit(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=1, stderr=""),
        MagicMock(returncode=0, stdout="abc123\trefs/tags/1.2.3\n"),
    ]

    assert find_existing_tag("1.2.3", tmp_path) == "on origin"

    local_command = mock_run.call_args_list[0].args[0]
    remote_command = mock_run.call_args_list[1].args[0]
    assert local_command[0].lower().endswith(("git", "git.exe"))
    assert local_command[1:] == ["rev-parse", "-q", "--verify", "refs/tags/1.2.3"]
    assert remote_command[0].lower().endswith(("git", "git.exe"))
    assert remote_command[1:] == [
        "ls-remote",
        "--exit-code",
        "--tags",
        "origin",
        "refs/tags/1.2.3",
    ]


@patch("release_tool.bat_runner.subprocess.run")
def test_find_existing_tag_returns_none_when_missing_locally_and_on_origin(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=1, stderr=""),
        MagicMock(returncode=2, stderr=""),
    ]

    assert find_existing_tag("1.2.3", tmp_path) is None


@patch("release_tool.bat_runner.subprocess.run")
def test_find_existing_tag_warns_and_continues_when_origin_check_fails(
    mock_run: MagicMock, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=1, stderr=""),
        MagicMock(returncode=128, stderr="network unavailable"),
    ]

    assert find_existing_tag("1.2.3", tmp_path) is None
    assert "Could not check origin tags" in caplog.text


@patch("release_tool.bat_runner.subprocess.run")
def test_find_existing_tag_raises_when_local_git_check_fails(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value.returncode = 128
    mock_run.return_value.stderr = "not a repository"

    with pytest.raises(ReleaseCreateError, match="exit 128"):
        find_existing_tag("1.2.3", tmp_path)


@patch("release_tool.bat_runner.subprocess.run")
def test_find_existing_tag_warns_and_continues_when_origin_cannot_start(
    mock_run: MagicMock, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    mock_run.side_effect = [MagicMock(returncode=1, stderr=""), OSError("missing git")]

    assert find_existing_tag("1.2.3", tmp_path) is None
    assert "Could not check origin tags" in caplog.text
