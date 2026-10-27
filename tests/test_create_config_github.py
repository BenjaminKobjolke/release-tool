"""Tests for GitHub Release configuration parsing."""

from pathlib import Path

import pytest

from release_tool.create_config import CreateConfig
from release_tool.exceptions import ConfigurationError


class TestCreateConfigGitHub:
    """Tests for the optional GitHub Release section."""

    def test_github_release_absent_by_default(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nscope = a\n")

        config = CreateConfig.from_ini_file(config_path)

        assert config.github_release is None

    def test_github_release_disabled_section_ignored(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text(
            "[Release]\nscope = a\n[GitHubRelease]\nenabled = false\nassets = a.exe\n"
        )

        config = CreateConfig.from_ini_file(config_path)

        assert config.github_release is None

    def test_github_release_enabled_parses_assets_and_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text(
            "[Release]\nscope = a\n[GitHubRelease]\nenabled = true\nassets = target/app.exe\n"
        )

        config = CreateConfig.from_ini_file(config_path)

        assert config.github_release is not None
        assert config.github_release.assets == ["target/app.exe"]
        assert config.github_release.repo is None
        assert config.github_release.tag_format == "{label}"
        assert config.github_release.title_format == "{label}"

    def test_github_release_full_overrides(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text(
            "[Release]\nscope = a\n"
            "[GitHubRelease]\n"
            "enabled = true\n"
            "assets = target/app.exe, target/app.zip\n"
            "repo = owner/name\n"
            "tag_format = v{label}\n"
            "title_format = App {label}\n"
        )

        config = CreateConfig.from_ini_file(config_path)

        assert config.github_release is not None
        assert config.github_release.assets == ["target/app.exe", "target/app.zip"]
        assert config.github_release.repo == "owner/name"
        assert config.github_release.tag_format == "v{label}"
        assert config.github_release.title_format == "App {label}"

    def test_github_release_enabled_without_assets_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "release_create.ini"
        config_path.write_text("[Release]\nscope = a\n[GitHubRelease]\nenabled = true\n")

        with pytest.raises(ConfigurationError, match="assets"):
            CreateConfig.from_ini_file(config_path)
