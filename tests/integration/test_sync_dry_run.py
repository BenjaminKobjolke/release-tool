"""Integration test: `release-tool sync --dry-run` end-to-end.

Exercises the real CLI dispatch + config load + walk against a throwaway tree.
Needs no platform skip: a dry run never opens an FTP connection.
"""

from pathlib import Path

import pytest

from release_tool.cli import main

CONFIG = """[FTP]
host = ftp.example.com
username = testuser
password = testpass
remote_path = /

[Sync]
local_dir = releases
exclude = windows/**
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway project with a releases tree and a sync config."""
    releases = tmp_path / "releases"
    (releases / "windows").mkdir(parents=True)
    (releases / "linux").mkdir()
    (releases / "linux" / "app.tar").write_bytes(b"linux-app")
    (releases / "windows" / "app.exe").write_bytes(b"windows-app")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "sync.ini").write_text(CONFIG, encoding="utf-8")
    return tmp_path


def test_dry_run_lists_included_files_only(project: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The dry run reports the included file and never mentions the excluded one."""
    with caplog.at_level("INFO"):
        exit_code = main(
            [
                "sync",
                str(project / "tools" / "sync.ini"),
                "--project-root",
                str(project),
                "--dry-run",
            ]
        )

    assert exit_code == 0
    assert "/linux/app.tar" in caplog.text
    assert "app.exe" not in caplog.text


def test_missing_local_dir_exits_nonzero(tmp_path: Path) -> None:
    """A config pointing at nothing fails instead of reporting success."""
    (tmp_path / "sync.ini").write_text(CONFIG, encoding="utf-8")

    assert main(["sync", str(tmp_path / "sync.ini"), "--project-root", str(tmp_path)]) == 1
