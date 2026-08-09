"""Configuration for the `create` (full-release orchestration) subcommand.

Mirrors the pattern in ``config.py``: a dataclass plus a ``from_ini_file``
classmethod backed by stdlib ``configparser``. Only per-project differences need
to be set; everything else falls back to the conventional defaults below.
"""

import configparser
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError

DEFAULT_SCOPE = "app"
DEFAULT_NOTES_DIR = "release_notes"
DEFAULT_EN_FILE = "en.json"
DEFAULT_LABEL_FORMAT = "{version}_{build}"

# Conventional bat paths (relative to the project root). `publish` has no default
# on purpose: an absent/empty publish bat means "build, then stop" (no publish,
# no commit, no tag).
DEFAULT_BATS = {
    "version_get": "tools/version_get.bat",
    "build_get": "tools/build_get.bat",
    "build_increment": "tools/build_increment.bat",
    "build_decrement": "tools/build_decrement.bat",
    "translate": "tools/translator_app-release-notes.bat",
    "build": "tools/build_release.bat",
}


@dataclass
class BatsConfig:
    """Paths to the project's release batch files (relative to project root)."""

    version_get: str
    build_get: str
    build_increment: str
    build_decrement: str
    translate: str
    build: str
    publish: str | None  # None => build-and-stop (no publish, no commit/tag)


@dataclass
class CreateConfig:
    """Configuration for the full-release `create` workflow."""

    scope: str
    publish_platform: str
    notes_dir: str
    en_file: str
    label_format: str
    english_only: bool
    bats: BatsConfig

    @classmethod
    def from_ini_file(cls, path: Path) -> "CreateConfig":
        """Load create configuration from an INI file."""
        if not path.exists():
            raise ConfigurationError(f"Create configuration file not found: {path}")

        parser = configparser.ConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except configparser.Error as e:
            raise ConfigurationError(
                f"Failed to parse create configuration file: {e}"
            ) from e

        release_section = parser["Release"] if "Release" in parser else {}
        bats_section = parser["Bats"] if "Bats" in parser else {}

        try:
            english_only = _getboolean(parser, "Release", "english_only", False)
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid 'english_only' value (expected true/false): {e}"
            ) from e

        publish_raw = bats_section.get("publish", "").strip()
        bats = BatsConfig(
            version_get=bats_section.get("version_get", DEFAULT_BATS["version_get"]).strip(),
            build_get=bats_section.get("build_get", DEFAULT_BATS["build_get"]).strip(),
            build_increment=bats_section.get(
                "build_increment", DEFAULT_BATS["build_increment"]
            ).strip(),
            build_decrement=bats_section.get(
                "build_decrement", DEFAULT_BATS["build_decrement"]
            ).strip(),
            translate=bats_section.get("translate", DEFAULT_BATS["translate"]).strip(),
            build=bats_section.get("build", DEFAULT_BATS["build"]).strip(),
            publish=publish_raw or None,
        )

        return cls(
            scope=release_section.get("scope", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE,
            publish_platform=release_section.get("publish_platform", "").strip(),
            notes_dir=release_section.get("notes_dir", DEFAULT_NOTES_DIR).strip()
            or DEFAULT_NOTES_DIR,
            en_file=release_section.get("en_file", DEFAULT_EN_FILE).strip() or DEFAULT_EN_FILE,
            label_format=release_section.get("label_format", DEFAULT_LABEL_FORMAT).strip()
            or DEFAULT_LABEL_FORMAT,
            english_only=english_only,
            bats=bats,
        )


def _getboolean(
    parser: configparser.ConfigParser, section: str, key: str, default: bool
) -> bool:
    """Read a boolean, returning ``default`` when the section/key is absent."""
    if section not in parser or key not in parser[section]:
        return default
    return bool(parser[section].getboolean(key))
