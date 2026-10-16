"""Tests for the mac-package CLI."""

from pathlib import Path
from unittest.mock import patch

from release_tool.cli import main
from release_tool.cli_mac import parse_mac_package_args


class TestParseMacPackageArgs:
    def test_defaults_and_flags(self) -> None:
        args = parse_mac_package_args(["tool", "mac.ini"])
        assert args.binary == Path("tool")
        assert args.config == Path("mac.ini")
        assert args.project_root == Path.cwd()
        assert not args.dry_run and not args.verbose

        args = parse_mac_package_args(
            ["tool", "mac.ini", "--project-root", "project", "--dry-run", "--verbose"]
        )
        assert args.project_root == Path("project")
        assert args.dry_run and args.verbose


class TestMacPackageDispatch:
    def test_main_dispatches_to_mac_runner(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        config = tmp_path / "mac.ini"
        config.write_text(
            """[MacPackage]
identifier = com.example.tool
install_location = /usr/local/bin/tool
version = 1.0
output = tool.pkg

[MacSigning]
app_identity = App
installer_identity = Installer
keychain_profile = profile
""",
            encoding="utf-8",
        )
        with patch("release_tool.cli_mac.MacPackager") as runner:
            runner.return_value.package.return_value = tmp_path / "tool.pkg"
            assert main(["mac-package", str(binary), str(config), "--dry-run"]) == 0
        runner.return_value.package.assert_called_once_with(binary)

    def test_non_macos_returns_error_code_one(self, tmp_path: Path) -> None:
        binary = tmp_path / "tool"
        binary.touch()
        config = tmp_path / "mac.ini"
        config.write_text(
            """[MacPackage]
identifier = x
install_location = /usr/local/bin/x
version = 1
output = x.pkg

[MacSigning]
app_identity = app
installer_identity = installer
keychain_profile = profile
""",
            encoding="utf-8",
        )
        with patch("release_tool.mac_package.sys.platform", "win32"):
            exit_code = main(
                ["mac-package", str(binary), str(config), "--project-root", str(tmp_path)]
            )
        assert exit_code == 1
