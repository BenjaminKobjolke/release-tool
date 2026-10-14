"""The FTP check batch wrapper must return the command's exit code to its caller.

The Tickets Watcher reads a batch command's process exit code as its result.
Windows-only because this test invokes ``cmd /c`` on a .bat file.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="the FTP check launcher is a Windows .bat file"
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_check_ftp_bat_propagates_configuration_error(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles.ini"
    profiles.write_text("", encoding="utf-8")

    result = subprocess.run(
        [
            "cmd",
            "/c",
            str(REPO_ROOT / "tools" / "check_ftp.bat"),
            "--profiles",
            str(profiles),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode == 2
    assert b"No FTP profiles" in result.stdout + result.stderr
