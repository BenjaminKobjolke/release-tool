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
# The example launcher hardcodes the release-tool checkout it cd's into; swap it for
# this checkout so the test does not depend on where the repo lives.
EXAMPLE_LAUNCHER_REPO_LITERAL = "D:\\GIT\\BenjaminKobjolke\\release-tool"


def _install_example_launcher(tmp_path: Path) -> Path:
    """Copy the example launcher into a temp project's `tools\\`, pointing at this repo."""
    tools = tmp_path / "tools"
    tools.mkdir()
    launcher = tools / "release_create.bat"
    example = (REPO_ROOT / "examples" / "release_create.bat").read_text(encoding="utf-8")
    launcher.write_text(
        example.replace(EXAMPLE_LAUNCHER_REPO_LITERAL, str(REPO_ROOT)), encoding="utf-8"
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
