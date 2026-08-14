"""Tests for the create-subcommand configuration."""

from pathlib import Path

import pytest

from release_tool.create_config import CreateConfig
from release_tool.exceptions import ConfigurationError


class TestCreateConfig:
    """Tests for CreateConfig.from_ini_file."""

    def test_minimal(self, tmp_path: Path) -> None:
        """A minimal INI falls back to conventional defaults."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nscope = myapp\npublish_platform = Play Store\n")

        config = CreateConfig.from_ini_file(config_path)

        assert config.scope == "myapp"
        assert config.publish_platform == "Play Store"
        assert config.notes_dir == "release_notes"
        assert config.en_file == "en.json"
        assert config.label_format == "{version}_{build}"
        assert config.versioning == "build"
        assert config.english_only is False
        assert config.bats.version_get == "tools/version_get.bat"
        assert config.bats.build == "tools/build_release.bat"
        # publish has no default -> None means build-and-stop
        assert config.bats.publish is None

    def test_full_overrides(self, tmp_path: Path) -> None:
        """Every value can be overridden, including a publish bat."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text(
            "[Release]\n"
            "scope = tool\n"
            "publish_platform = Website\n"
            "notes_dir = assets/notes\n"
            "en_file = english.json\n"
            "label_format = v{version}-{build}\n"
            "english_only = true\n"
            "[Bats]\n"
            "version_get = tools/ver.bat\n"
            "build = scripts/build.bat\n"
            "publish = tools/publish.bat\n"
        )

        config = CreateConfig.from_ini_file(config_path)

        assert config.notes_dir == "assets/notes"
        assert config.en_file == "english.json"
        assert config.label_format == "v{version}-{build}"
        assert config.english_only is True
        assert config.bats.version_get == "tools/ver.bat"
        assert config.bats.build == "scripts/build.bat"
        assert config.bats.publish == "tools/publish.bat"
        # untouched bats keep defaults
        assert config.bats.build_increment == "tools/build_increment.bat"

    def test_empty_publish_means_no_publish(self, tmp_path: Path) -> None:
        """An explicitly empty publish value is treated as build-and-stop."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nscope = a\n[Bats]\npublish =\n")

        config = CreateConfig.from_ini_file(config_path)

        assert config.bats.publish is None

    def test_defaults_when_no_sections(self, tmp_path: Path) -> None:
        """A file with no known sections still yields defaults."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Unrelated]\nx = 1\n")

        config = CreateConfig.from_ini_file(config_path)

        assert config.scope == "app"
        assert config.bats.publish is None

    def test_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            CreateConfig.from_ini_file(tmp_path / "missing.ini")

    def test_invalid_english_only(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nenglish_only = maybe\n")

        with pytest.raises(ConfigurationError, match="english_only"):
            CreateConfig.from_ini_file(config_path)

    def test_notes_label_format_defaults_to_label_format(self, tmp_path: Path) -> None:
        """Absent notes_label_format mirrors label_format (notes folder == commit label)."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nlabel_format = {version}+{build}\n")

        config = CreateConfig.from_ini_file(config_path)

        assert config.notes_label_format == "{version}+{build}"

    def test_notes_label_format_override(self, tmp_path: Path) -> None:
        """notes_label_format decouples the notes-folder key from the commit label."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text(
            "[Release]\nlabel_format = {version}+{build}\nnotes_label_format = {build}\n"
        )

        config = CreateConfig.from_ini_file(config_path)

        assert config.label_format == "{version}+{build}"
        assert config.notes_label_format == "{build}"

    def test_versioning_semver(self, tmp_path: Path) -> None:
        """versioning = semver is parsed (case-insensitive)."""
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nversioning = SemVer\n")

        config = CreateConfig.from_ini_file(config_path)

        assert config.versioning == "semver"

    def test_invalid_versioning(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nversioning = calver\n")

        with pytest.raises(ConfigurationError, match="versioning"):
            CreateConfig.from_ini_file(config_path)
