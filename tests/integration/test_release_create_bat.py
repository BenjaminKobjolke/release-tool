"""Integration test: the example `release_create.bat` launcher propagates the exit code.

`examples/release_create.bat` is the template projects copy into `tools/`, so it must
hand `release-tool`'s exit code back to the caller: the Tickets Watcher app reads a
command run's process exit code as its result. A trailing `cd` used to reset
`ERRORLEVEL` to 0, so a failed release read back as success. Windows-only, because it
invokes `cmd /c` on a .bat file.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="the launcher is a Windows .bat file"
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _install_example_launcher(tmp_path: Path) -> Path:
    """Copy the example launcher into a temp project's `tools\\`, pointing at this repo.

    The launcher reads the release-tool checkout from the project's `tools\\config.bat`,
    so the test writes one naming this checkout.
    """
    tools = tmp_path / "tools"
    tools.mkdir()
    launcher = tools / "release_create.bat"
    launcher.write_bytes((REPO_ROOT / "examples" / "release_create.bat").read_bytes())
    (tools / "config.bat").write_text(
        f'@echo off\r\nset "RELEASE_TOOL_DIR={REPO_ROOT}"\r\n', encoding="utf-8", newline=""
    )
    return launcher


def test_example_launcher_propagates_failure_exit_code(tmp_path: Path) -> None:
    launcher = _install_example_launcher(tmp_path)

    result = subprocess.run(
        ["cmd", "/c", str(launcher), "--bogus-arg"],
        capture_output=True,
        timeout=120,
    )

    # An unknown argument makes argparse exit 2 before any build or mutation; a launcher
    # that swallows the code (the pre-fix `cd /d "%~dp0"`) would report 0 here.
    assert result.returncode == 2
    # The launcher's own config preflight also exits 2 — make sure argparse was reached.
    assert b"--bogus-arg" in result.stderr


def test_example_launcher_fails_without_config_bat(tmp_path: Path) -> None:
    launcher = _install_example_launcher(tmp_path)
    (launcher.parent / "config.bat").unlink()

    result = subprocess.run(["cmd", "/c", str(launcher)], capture_output=True, timeout=120)

    assert result.returncode == 2
    assert b"config.bat not found" in result.stdout
