"""Tests for macOS package configuration."""

from pathlib import Path

import pytest

from release_tool.exceptions import ConfigurationError
from release_tool.mac_config import DEFAULT_ENTITLEMENTS, MacPackageConfig


def write_package(root: Path, version: str = "2.3.4") -> Path:
    """Create a valid app config and its referenced files."""
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "postinstall").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "version.txt").write_text(f" {version} \n", encoding="utf-8")
    path = root / "mac_package.ini"
    path.write_text(
        """[MacPackage]
identifier = com.example.tool
install_location = /usr/local/bin/tool
scripts = scripts
version_file = version.txt
output = dist/tool-{version}.pkg
""",
        encoding="utf-8",
    )
    return path


def write_signing(path: Path, app: str = "App Identity") -> None:
    """Write a shared signing file."""
    path.write_text(
        f"""[MacSigning]
app_identity = {app}
installer_identity = Installer Identity
keychain_profile = profile
""",
        encoding="utf-8",
    )


class TestMacPackageConfig:
    def test_loads_shared_signing_and_resolves_app_paths(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        shared = tmp_path / "shared.ini"
        write_signing(shared)

        config = MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

        assert config.app_identity == "App Identity"
        assert config.version == "2.3.4"
        assert config.output == tmp_path / "dist" / "tool-2.3.4.pkg"
        assert config.scripts == tmp_path / "scripts"
        assert config.entitlements == DEFAULT_ENTITLEMENTS
        assert config.entitlements.is_file()

    def test_app_signing_values_override_shared(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        ini.write_text(
            ini.read_text(encoding="utf-8") + "\n[MacSigning]\napp_identity = App Override\n",
            encoding="utf-8",
        )
        shared = tmp_path / "shared.ini"
        write_signing(shared)

        config = MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

        assert config.app_identity == "App Override"
        assert config.installer_identity == "Installer Identity"

    def test_app_signing_can_supply_every_shared_value(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        ini.write_text(
            ini.read_text(encoding="utf-8")
            + "\n[MacSigning]\napp_identity = App\ninstaller_identity = Installer\n"
            "keychain_profile = profile\n",
            encoding="utf-8",
        )

        assert MacPackageConfig.from_ini_file(ini, tmp_path).keychain_profile == "profile"

    def test_missing_signing_names_both_files(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        shared = tmp_path / "missing-shared.ini"

        with pytest.raises(ConfigurationError) as error:
            MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

        assert str(ini) in str(error.value)
        assert str(shared) in str(error.value)

    def test_version_value_and_file_are_mutually_exclusive(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        shared = tmp_path / "shared.ini"
        write_signing(shared)
        content = ini.read_text(encoding="utf-8").replace(
            "version_file = version.txt", "version = 1.0\nversion_file = version.txt"
        )
        ini.write_text(content, encoding="utf-8")

        with pytest.raises(ConfigurationError, match="exactly one"):
            MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

    def test_empty_version_file_is_rejected(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        (tmp_path / "version.txt").write_text(" \n", encoding="utf-8")
        shared = tmp_path / "shared.ini"
        write_signing(shared)

        with pytest.raises(ConfigurationError, match="version"):
            MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

    @pytest.mark.parametrize("key", ["identifier", "install_location", "output"])
    def test_required_package_values(self, tmp_path: Path, key: str) -> None:
        ini = write_package(tmp_path)
        ini.write_text(
            "\n".join(
                line
                for line in ini.read_text(encoding="utf-8").splitlines()
                if not line.startswith(f"{key} =")
            ),
            encoding="utf-8",
        )
        shared = tmp_path / "shared.ini"
        write_signing(shared)

        with pytest.raises(ConfigurationError, match=key):
            MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

    def test_custom_entitlements_must_exist(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        with ini.open("a", encoding="utf-8") as file:
            file.write("entitlements = missing.plist\n")
        shared = tmp_path / "shared.ini"
        write_signing(shared)

        with pytest.raises(ConfigurationError, match="entitlements"):
            MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)

    def test_scripts_must_be_an_existing_folder(self, tmp_path: Path) -> None:
        ini = write_package(tmp_path)
        (tmp_path / "scripts" / "postinstall").unlink()
        (tmp_path / "scripts").rmdir()
        (tmp_path / "scripts").write_text("not a folder", encoding="utf-8")
        shared = tmp_path / "shared.ini"
        write_signing(shared)

        with pytest.raises(ConfigurationError, match="scripts"):
            MacPackageConfig.from_ini_file(ini, tmp_path, signing_path=shared)
