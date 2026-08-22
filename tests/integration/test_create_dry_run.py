"""Integration test: `release-tool create --dry-run` end-to-end.

Exercises the real CLI dispatch + config load + label computation against a
throwaway project with real (echoing) version/build bats. Only the read-only
version/build bats actually execute; every mutating step is dry-run logged.
Windows-only, because it invokes `cmd /c call` on .bat files.
"""

import sys
from pathlib import Path

import pytest

from release_tool.cli import main

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="create workflow shells out to Windows .bat files"
)


def _make_project(root: Path) -> None:
    tools = root / "tools"
    tools.mkdir()
    (tools / "version_get.bat").write_text("@echo off\necho 1.0.0\n")
    (tools / "build_get.bat").write_text("@echo off\necho 21\n")
    # Mutating bats are never executed under --dry-run, but must exist as paths.
    for name in (
        "build_increment",
        "build_decrement",
        "build_release",
        "translator_app-release-notes",
        "publish_release",
    ):
        (tools / f"{name}.bat").write_text("@echo off\n")

    notes = root / "release_notes" / "1.0.0_22"
    notes.mkdir(parents=True)
    (notes / "en.json").write_text('{"notes": ["x"]}')

    (root / "release_create.ini").write_text(
        "[Release]\nscope = demo\npublish_platform = Website\n"
        "[Bats]\npublish = tools/publish_release.bat\n"
    )


def test_create_dry_run_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["create", "release_create.ini", "--dry-run"])

    assert exit_code == 0


def test_create_missing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(["create", "release_create.ini", "--dry-run"])

    assert exit_code == 2  # ConfigurationError


def _make_semver_project(root: Path) -> None:
    """A semver project: version_get prints a bare X.Y.Z, no build counter."""
    tools = root / "tools"
    tools.mkdir()
    (tools / "get_version.bat").write_text("@echo off\necho 0.1.6\n")
    for name in (
        "increment_version",
        "decrement_version",
        "build",
        "translator_release_notes",
        "publish_release",
    ):
        (tools / f"{name}.bat").write_text("@echo off\n")

    notes = root / "release_notes" / "0.1.7"
    notes.mkdir(parents=True)
    (notes / "en.json").write_text('{"notes": ["x"]}')

    (root / "release_create.ini").write_text(
        "[Release]\nscope = calc\npublish_platform = Website\nversioning = semver\n"
        "[Bats]\nversion_get = tools/get_version.bat\n"
        "build_increment = tools/increment_version.bat\n"
        "build_decrement = tools/decrement_version.bat\n"
        "translate = tools/translator_release_notes.bat\n"
        "build = tools/build.bat\npublish = tools/publish_release.bat\n"
    )


def test_create_dry_run_semver_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_semver_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["create", "release_create.ini", "--dry-run"])

    assert exit_code == 0


def _make_self_contained_multichannel_project(root: Path) -> None:
    """A monolithic build bat (bump+translate+build) + two gated publish channels."""
    tools = root / "tools"
    tools.mkdir()
    (tools / "version_get.bat").write_text("@echo off\necho 1.0.0\n")
    (tools / "build_get.bat").write_text("@echo off\necho 21\n")
    for name in ("build_release", "publish_website", "publish_play"):
        (tools / f"{name}.bat").write_text("@echo off\n")

    notes = root / "release_notes" / "1.0.0_22"
    notes.mkdir(parents=True)
    (notes / "en.json").write_text('{"notes": ["x"]}')

    (root / "release_create.ini").write_text(
        "[Release]\nscope = demo\npublish_platform = Website, Google Play\n"
        "build_self_contained = true\n"
        "[Bats]\nbuild = tools/build_release.bat\n"
        "publish = tools/publish_website.bat, tools/publish_play.bat\n"
    )


def test_create_dry_run_self_contained_multichannel_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_self_contained_multichannel_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["create", "release_create.ini", "--dry-run"])

    assert exit_code == 0
