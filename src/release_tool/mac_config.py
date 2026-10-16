"""Configuration for building and signing a macOS installer package."""

import configparser
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .config import load_parser
from .exceptions import ConfigurationError

SIGNING_SECTION = "MacSigning"
PACKAGE_SECTION = "MacPackage"
VERSION_PLACEHOLDER = "{version}"
MAC_SIGNING_FILE = Path(__file__).resolve().parents[2] / "mac_signing.ini"
DEFAULT_ENTITLEMENTS = Path(__file__).with_name("mac_entitlements.plist").resolve()


@dataclass(frozen=True)
class MacPackageConfig:
    """All app and shared signing values needed for one package build."""

    app_identity: str
    installer_identity: str
    keychain_profile: str
    entitlements: Path
    identifier: str
    install_location: str
    scripts: Path | None
    version: str
    output: Path

    @classmethod
    def from_ini_file(
        cls, path: Path, project_root: Path, signing_path: Path | None = None
    ) -> "MacPackageConfig":
        """Load an app INI and merge its signing values over the shared signing file."""
        app_parser = load_parser(path)
        app_signing = _section(app_parser, SIGNING_SECTION)
        shared_path = MAC_SIGNING_FILE if signing_path is None else signing_path
        shared_signing: Mapping[str, str] = {}
        if shared_path.exists():
            shared_signing = _section(load_parser(shared_path), SIGNING_SECTION)
        signing = {**shared_signing, **app_signing}
        missing_signing = [
            key
            for key in ("app_identity", "installer_identity", "keychain_profile")
            if not signing.get(key, "").strip()
        ]
        if missing_signing:
            raise ConfigurationError(
                f"Missing MacSigning value(s) {', '.join(missing_signing)} in "
                f"{path} or shared signing file {shared_path}"
            )

        package = _section(app_parser, PACKAGE_SECTION)
        identifier = _required(package, "identifier")
        install_location = _required(package, "install_location")
        raw_output = _required(package, "output")
        raw_version = package.get("version", "").strip()
        raw_version_file = package.get("version_file", "").strip()
        if bool(raw_version) == bool(raw_version_file):
            raise ConfigurationError(
                "MacPackage requires exactly one of 'version' or 'version_file'"
            )
        if raw_version_file:
            version_path = _resolve(project_root, raw_version_file)
            if not version_path.is_file():
                raise ConfigurationError(f"MacPackage version_file not found: {version_path}")
            version = version_path.read_text(encoding="utf-8").strip()
            if not version:
                raise ConfigurationError(f"MacPackage version_file is empty: {version_path}")
        else:
            version = raw_version

        output = _resolve(project_root, raw_output.replace(VERSION_PLACEHOLDER, version))
        raw_entitlements = package.get("entitlements", "").strip()
        entitlements = (
            _resolve(project_root, raw_entitlements) if raw_entitlements else DEFAULT_ENTITLEMENTS
        )
        if not entitlements.is_file():
            raise ConfigurationError(f"MacPackage entitlements file not found: {entitlements}")

        raw_scripts = package.get("scripts", "").strip()
        scripts = _resolve(project_root, raw_scripts) if raw_scripts else None
        if scripts is not None and not scripts.is_dir():
            raise ConfigurationError(f"MacPackage scripts must be an existing folder: {scripts}")

        return cls(
            app_identity=signing["app_identity"].strip(),
            installer_identity=signing["installer_identity"].strip(),
            keychain_profile=signing["keychain_profile"].strip(),
            entitlements=entitlements,
            identifier=identifier,
            install_location=install_location,
            scripts=scripts,
            version=version,
            output=output,
        )


def _section(parser: configparser.ConfigParser, name: str) -> Mapping[str, str]:
    """Return a normalized section mapping, or an empty mapping when absent."""
    if name not in parser:
        return {}
    return parser[name]


def _required(values: Mapping[str, str], key: str) -> str:
    """Read one required, non-blank package value."""
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"MacPackage '{key}' is required")
    return value


def _resolve(root: Path, value: str) -> Path:
    """Resolve configured paths against the app project root."""
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()
