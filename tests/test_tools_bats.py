"""Keep tools launchers compatible with tools/TICKETS_WATCHER_COMMANDS.md.

The Tickets Watcher reads their exit codes and a bare pause would hang a run.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
LAUNCHERS = sorted((*TOOLS.rglob("*.bat"), *TOOLS.rglob("*.cmd")))


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda path: str(path.relative_to(TOOLS)))
def test_launcher_is_watcher_compatible(launcher: Path) -> None:
    lines = [
        stripped
        for raw in launcher.read_text(encoding="utf-8").splitlines()
        if (stripped := raw.strip().lower())
    ]
    assert lines[-1].startswith("exit /b")
    assert "pause" not in lines
