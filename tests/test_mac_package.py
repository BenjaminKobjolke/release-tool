"""Tests for the macOS package command runner."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from release_tool.exceptions import MacPackageError
from release_tool.mac_config import MacPackageConfig
from release_tool.mac_package import MacPackager


def make_config(root: Path, scripts: Path | None = None) -> MacPackageConfig:
    return MacPackageConfig(
        app_identity="Developer ID Application: Example",
        installer_identity="Developer ID Installer: Example",
        keychain_profile="profile",
        entitlements=root / "entitlements.plist",
        identifier="com.example.tool",
        install_location="/usr/local/bin/tool",
        scripts=scripts,
        version="1.2.3",
        output=root / "out" / "tool.pkg",
    )


class TestMacPackager:
    def test_runs_commands_in_order_with_staged_binary(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.write_bytes(b"binary")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        config = make_config(tmp_path, scripts)
        staged_contents: list[bytes] = []
        events: list[str] = []

        def record_stage(command: list[str], cwd: Path, dry_run: bool = False) -> None:
            events.append("staple" if command[:2] == ["xcrun", "stapler"] else command[0])
            if command[0] == "pkgbuild":
                staged_contents.append((Path(command[2]) / binary.name).read_bytes())

        def record_notary(command: list[str], cwd: Path) -> str:
            events.append("notarytool")
            return json.dumps({"status": "Accepted", "id": "submission-1"})

        with (
            patch("release_tool.mac_tools.sys.platform", "darwin"),
            patch(
                "release_tool.mac_package.run_command", autospec=True, side_effect=record_stage
            ) as run,
            patch(
                "release_tool.mac_tools.capture_command",
                autospec=True,
                side_effect=record_notary,
            ) as capture,
        ):
            result = MacPackager(config).package(binary)

        assert result == config.output
        commands = [entry.args[0] for entry in run.call_args_list]
        assert commands[0] == [
            "codesign",
            "--force",
            "--options=runtime",
            "--entitlements",
            str(config.entitlements),
            "--sign",
            config.app_identity,
            "--timestamp",
            str(binary),
        ]
        stage = commands[1][2]
        assert commands[1] == [
            "pkgbuild",
            "--root",
            stage,
            "--install-location",
            config.install_location,
            "--scripts",
            str(scripts),
            "--identifier",
            config.identifier,
            "--version",
            config.version,
            "--sign",
            config.installer_identity,
            str(config.output),
        ]
        assert commands[2] == ["xcrun", "stapler", "staple", str(config.output)]
        assert commands[3] == ["pkgutil", "--check-signature", str(config.output)]
        assert commands[4] == [
            "spctl",
            "--assess",
            "--type",
            "install",
            "--verbose",
            str(config.output),
        ]
        capture.assert_called_once_with(
            [
                "xcrun",
                "notarytool",
                "submit",
                str(config.output),
                "--keychain-profile",
                "profile",
                "--wait",
                "--output-format",
                "json",
            ],
            cwd=config.output.parent,
        )
        assert staged_contents == [b"binary"]
        assert events == ["codesign", "pkgbuild", "notarytool", "staple", "pkgutil", "spctl"]
        assert all(entry.kwargs["cwd"] == config.output.parent for entry in run.call_args_list)
        assert config.output.parent.is_dir()

    def test_pkgbuild_omits_scripts_when_unconfigured(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        config = make_config(tmp_path)
        with (
            patch("release_tool.mac_tools.sys.platform", "darwin"),
            patch("release_tool.mac_package.run_command", autospec=True) as run,
            patch("release_tool.mac_tools.capture_command", autospec=True) as capture,
        ):
            capture.return_value = '{"status":"Accepted"}'
            MacPackager(config).package(binary)

        assert "--scripts" not in run.call_args_list[1].args[0]

    def test_notarization_rejection_stops_before_stapling(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        config = make_config(tmp_path)
        with (
            patch("release_tool.mac_tools.sys.platform", "darwin"),
            patch("release_tool.mac_package.run_command", autospec=True) as run,
            patch("release_tool.mac_tools.capture_command", autospec=True) as capture,
        ):
            capture.side_effect = ['{"status":"Invalid","id":"bad-id"}', "issue details"]
            with pytest.raises(MacPackageError, match="bad-id"):
                MacPackager(config).package(binary)

        assert capture.call_args_list[1].args[0] == [
            "xcrun",
            "notarytool",
            "log",
            "bad-id",
            "--keychain-profile",
            "profile",
        ]
        assert len(run.call_args_list) == 2

    def test_invalid_notary_output_is_rejected(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        with (
            patch("release_tool.mac_tools.sys.platform", "darwin"),
            patch("release_tool.mac_package.run_command", autospec=True),
            patch("release_tool.mac_tools.capture_command", autospec=True, return_value="oops"),
            pytest.raises(MacPackageError, match="notarytool"),
        ):
            MacPackager(make_config(tmp_path)).package(binary)

    def test_non_macos_real_run_fails_before_commands(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        with (
            patch("release_tool.mac_tools.sys.platform", "win32"),
            patch("release_tool.mac_package.run_command", autospec=True) as run,
            patch("release_tool.mac_tools.capture_command", autospec=True) as capture,
            pytest.raises(MacPackageError, match="needs macOS"),
        ):
            MacPackager(make_config(tmp_path)).package(binary)
        run.assert_not_called()
        capture.assert_not_called()

    def test_non_macos_dry_run_logs_without_running_commands(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        with (
            patch("release_tool.mac_tools.sys.platform", "win32"),
            patch("release_tool.mac_package.run_command", autospec=True) as run,
            patch("release_tool.mac_tools.run_command", autospec=True) as tool_run,
            patch("release_tool.mac_tools.capture_command", autospec=True) as capture,
        ):
            result = MacPackager(make_config(tmp_path), dry_run=True).package(binary)
        assert result == make_config(tmp_path).output
        assert len(run.call_args_list) == 5
        assert len(tool_run.call_args_list) == 1
        assert all(entry.kwargs["dry_run"] for entry in run.call_args_list)
        assert all(entry.kwargs["dry_run"] for entry in tool_run.call_args_list)
        capture.assert_not_called()

    def test_missing_binary_fails(self, tmp_path: Path) -> None:
        with pytest.raises(MacPackageError, match="not found"):
            MacPackager(make_config(tmp_path)).package(tmp_path / "missing")
