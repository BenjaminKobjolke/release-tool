"""Focused tests for external command execution."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from release_tool.bat_runner import run_command


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
