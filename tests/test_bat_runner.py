"""Focused tests for external command execution."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.bat_runner import has_staged_changes, run_command
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
