"""Tests for pre-signing helpers and workflows."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from release_tool.authenticode import read_signer_name


class TestReadSignerName:
    """Cover the PowerShell subject parsing and its failure cases."""

    def test_returns_common_name(self, tmp_path: Path) -> None:
        file_path = tmp_path / "release.exe"
        result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="CN=XIDA GmbH, O=XIDA GmbH, C=DE", stderr=""
        )
        with patch("release_tool.authenticode.subprocess.run", return_value=result):
            assert read_signer_name(file_path) == "XIDA GmbH"

    @pytest.mark.parametrize(
        "result",
        [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="CN=ignored", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="  ", stderr=""),
        ],
    )
    def test_returns_none_for_invalid_signature_output(
        self, tmp_path: Path, result: subprocess.CompletedProcess[str]
    ) -> None:
        with patch("release_tool.authenticode.subprocess.run", return_value=result):
            assert read_signer_name(tmp_path / "release.exe") is None

    @pytest.mark.parametrize("error", [subprocess.TimeoutExpired("powershell", 30), OSError()])
    def test_returns_none_when_signature_command_fails(
        self, tmp_path: Path, error: Exception
    ) -> None:
        with patch("release_tool.authenticode.subprocess.run", side_effect=error):
            assert read_signer_name(tmp_path / "release.exe") is None
