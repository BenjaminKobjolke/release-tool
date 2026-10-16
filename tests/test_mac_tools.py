"""Tests for shared Apple command helpers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from release_tool.exceptions import MacPackageError, ReleaseToolError
from release_tool.mac_tools import check_notarization, require_macos


def test_check_notarization_accepts_accepted_result() -> None:
    with patch("release_tool.mac_tools.capture_command", autospec=True) as capture:
        check_notarization('{"status":"Accepted"}', "profile", Path.cwd())
    capture.assert_not_called()


def test_check_notarization_fetches_log_and_rejects(tmp_path: Path, caplog) -> None:
    with patch(
        "release_tool.mac_tools.capture_command", autospec=True, return_value="Apple issue details"
    ) as capture:
        with pytest.raises(MacPackageError, match="bad-id"):
            check_notarization('{"status":"Invalid","id":"bad-id"}', "profile", tmp_path)

    capture.assert_called_once_with(
        ["xcrun", "notarytool", "log", "bad-id", "--keychain-profile", "profile"],
        cwd=tmp_path,
    )
    assert "Apple issue details" in caplog.text


def test_check_notarization_log_failure_preserves_rejection(tmp_path: Path) -> None:
    with patch(
        "release_tool.mac_tools.capture_command",
        autospec=True,
        side_effect=ReleaseToolError("log unavailable"),
    ):
        with pytest.raises(MacPackageError, match="bad-id"):
            check_notarization('{"status":"Invalid","id":"bad-id"}', "profile", tmp_path)


def test_check_notarization_rejects_malformed_json(tmp_path: Path) -> None:
    with pytest.raises(MacPackageError, match="notarytool"):
        check_notarization("not-json", "profile", tmp_path)


def test_require_macos_guards_real_runs_but_allows_dry_run() -> None:
    with patch("release_tool.mac_tools.sys.platform", "win32"):
        with pytest.raises(MacPackageError, match="needs macOS"):
            require_macos("mac-sign", dry_run=False)
        require_macos("mac-sign", dry_run=True)
