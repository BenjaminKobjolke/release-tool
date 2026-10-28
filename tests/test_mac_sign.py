"""Tests for signing and notarizing macOS apps and disk images."""

from contextlib import AbstractContextManager
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from release_tool.exceptions import MacPackageError
from release_tool.mac_config import DEFAULT_ENTITLEMENTS, MacSignConfig
from release_tool.mac_sign import MacSigner


def make_config() -> MacSignConfig:
    return MacSignConfig(
        app_identity="Developer ID Application: Example",
        keychain_profile="profile",
    )


def patched_commands(
    events: list[str], commands: list[list[str]], submissions: list[str]
) -> tuple[
    AbstractContextManager[object],
    AbstractContextManager[object],
    AbstractContextManager[object],
]:
    def record_run(command: list[str], cwd: Path, dry_run: bool = False) -> None:
        commands.append(command)
        events.append(command[0] if command[:2] != ["xcrun", "stapler"] else command[2])

    def record_notary(command: list[str], cwd: Path) -> str:
        commands.append(command)
        events.append("notarytool")
        if command[2] == "submit":
            return submissions.pop(0)
        return "Apple issue details"

    return (
        patch("release_tool.mac_sign.run_command", autospec=True, side_effect=record_run),
        patch("release_tool.mac_tools.run_command", autospec=True, side_effect=record_run),
        patch("release_tool.mac_tools.capture_command", autospec=True, side_effect=record_notary),
    )


def test_signs_app_in_order_and_removes_notarization_zip(tmp_path: Path) -> None:
    app = tmp_path / "fman.app"
    app.mkdir()
    entitlements = tmp_path / "entitlements.plist"
    entitlements.write_text("plist", encoding="utf-8")
    events: list[str] = []
    commands: list[list[str]] = []
    patches = patched_commands(events, commands, ['{"status":"Accepted","id":"app-id"}'])

    with (
        patch("release_tool.mac_tools.sys.platform", "darwin"),
        patches[0],
        patches[1],
        patches[2],
    ):
        result = MacSigner(make_config()).sign(app, entitlements)

    assert result == app
    assert events == ["codesign", "ditto", "notarytool", "staple", "validate", "spctl"]
    zip_path = Path(commands[2][3])
    assert commands[0] == [
        "codesign",
        "--deep",
        "--force",
        "--options=runtime",
        "--timestamp",
        "--entitlements",
        str(entitlements),
        "--sign",
        "Developer ID Application: Example",
        str(app),
    ]
    assert commands[1] == [
        "ditto",
        "-c",
        "-k",
        "--sequesterRsrc",
        "--keepParent",
        str(app),
        str(zip_path),
    ]
    assert zip_path.name == "fman.zip"
    assert commands[2] == [
        "xcrun",
        "notarytool",
        "submit",
        str(zip_path),
        "--keychain-profile",
        "profile",
        "--wait",
        "--output-format",
        "json",
    ]
    assert commands[3:6] == [
        ["xcrun", "stapler", "staple", str(app)],
        ["xcrun", "stapler", "validate", str(app)],
        ["spctl", "--assess", "--type", "execute", "-vv", str(app)],
    ]
    assert not zip_path.exists()


def test_signs_dmg_without_entitlements_in_order(tmp_path: Path) -> None:
    dmg = tmp_path / "fman.dmg"
    dmg.touch()
    events: list[str] = []
    commands: list[list[str]] = []
    patches = patched_commands(events, commands, ['{"status":"Accepted"}'])

    with (
        patch("release_tool.mac_tools.sys.platform", "darwin"),
        patches[0],
        patches[1],
        patches[2],
    ):
        MacSigner(make_config()).sign(dmg)

    assert events == ["codesign", "notarytool", "staple", "validate", "spctl"]
    assert commands[0] == [
        "codesign",
        "--force",
        "--timestamp",
        "--sign",
        "Developer ID Application: Example",
        str(dmg),
    ]
    assert commands[1][3] == str(dmg)
    assert commands[2:] == [
        ["xcrun", "stapler", "staple", str(dmg)],
        ["xcrun", "stapler", "validate", str(dmg)],
        [
            "spctl",
            "--assess",
            "--type",
            "open",
            "--context",
            "context:primary-signature",
            "-vv",
            str(dmg),
        ],
    ]


def test_notarization_rejection_does_not_staple(tmp_path: Path) -> None:
    dmg = tmp_path / "fman.dmg"
    dmg.touch()
    events: list[str] = []
    commands: list[list[str]] = []
    patches = patched_commands(events, commands, ['{"status":"Invalid","id":"x"}'])

    with (
        patch("release_tool.mac_tools.sys.platform", "darwin"),
        patches[0],
        patches[1],
        patches[2],
        pytest.raises(MacPackageError, match="x"),
    ):
        MacSigner(make_config()).sign(dmg)

    assert events == ["codesign", "notarytool", "notarytool"]
    assert all("stapler" not in command for command in commands)


@pytest.mark.parametrize("suffix", [".zip", ".pkg", ".txt"])
def test_unknown_suffix_fails_without_commands(tmp_path: Path, suffix: str) -> None:
    target = tmp_path / f"artifact{suffix}"
    target.touch()
    with patch("release_tool.mac_sign.run_command", autospec=True) as run:
        with pytest.raises(MacPackageError, match=".app.*.dmg"):
            MacSigner(make_config()).sign(target)
    run.assert_not_called()


def test_app_must_be_directory_and_target_must_exist(tmp_path: Path) -> None:
    app_file = tmp_path / "not-a-bundle.app"
    app_file.touch()
    missing = tmp_path / "missing.dmg"

    with pytest.raises(MacPackageError, match="directory"):
        MacSigner(make_config()).sign(app_file)
    with pytest.raises(MacPackageError, match="not found"):
        MacSigner(make_config()).sign(missing)


def test_dmg_must_be_file(tmp_path: Path) -> None:
    dmg = tmp_path / "directory.dmg"
    dmg.mkdir()
    with pytest.raises(MacPackageError, match="file"):
        MacSigner(make_config()).sign(dmg)


def test_non_macos_real_run_fails_before_commands(tmp_path: Path) -> None:
    dmg = tmp_path / "fman.dmg"
    dmg.touch()
    with (
        patch("release_tool.mac_tools.sys.platform", "win32"),
        patch("release_tool.mac_sign.run_command", autospec=True) as run,
        pytest.raises(MacPackageError, match="needs macOS"),
    ):
        MacSigner(make_config()).sign(dmg)
    run.assert_not_called()


def test_non_macos_dry_run_logs_commands(tmp_path: Path) -> None:
    app = tmp_path / "fman.app"
    app.mkdir()
    events: list[str] = []
    commands: list[list[str]] = []
    patches = patched_commands(events, commands, [])

    with (
        patch("release_tool.mac_tools.sys.platform", "win32"),
        patches[0],
        patches[1],
        patches[2],
    ):
        result = MacSigner(make_config(), dry_run=True).sign(app)

    assert result == app
    assert events == ["codesign", "ditto", "xcrun", "staple", "validate", "spctl"]


def test_default_entitlements_used_and_missing_custom_file_rejected(tmp_path: Path) -> None:
    app = tmp_path / "fman.app"
    app.mkdir()
    events: list[str] = []
    commands: list[list[str]] = []
    patches = patched_commands(events, commands, ['{"status":"Accepted"}'])

    with (
        patch("release_tool.mac_tools.sys.platform", "darwin"),
        patches[0],
        patches[1],
        patches[2],
    ):
        MacSigner(make_config()).sign(app)

    assert commands[0][commands[0].index("--entitlements") + 1] == str(DEFAULT_ENTITLEMENTS)
    with patch("release_tool.mac_tools.sys.platform", "darwin"):
        with pytest.raises(MacPackageError, match="entitlements"):
            MacSigner(make_config()).sign(app, tmp_path / "missing.plist")


def test_entitlements_for_dmg_are_ignored(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO)
    dmg = tmp_path / "fman.dmg"
    dmg.touch()
    entitlements = tmp_path / "ignored.plist"
    entitlements.touch()
    events: list[str] = []
    commands: list[list[str]] = []
    patches = patched_commands(events, commands, ['{"status":"Accepted"}'])

    with (
        patch("release_tool.mac_tools.sys.platform", "darwin"),
        patches[0],
        patches[1],
        patches[2],
    ):
        MacSigner(make_config()).sign(dmg, entitlements)

    assert "--entitlements" not in commands[0]
    assert "Ignoring --entitlements" in caplog.text
