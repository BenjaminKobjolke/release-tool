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
    for name in ("build_increment", "build_decrement", "build_release",
                 "translator_app-release-notes", "publish_release"):
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
