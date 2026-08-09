"""Shared runner for external commands (batch files, git, codex).

Every ``.bat`` / git / codex call in the create workflow goes through here so
command execution, error handling, and dry-run behavior live in one place.
"""

import logging
import os
import subprocess
from pathlib import Path

from .exceptions import ReleaseCreateError

logger = logging.getLogger(__name__)


def bat_command(bat_path: str) -> list[str]:
    """Build the argv for a Windows batch file.

    ``cmd /c call`` is required so a bat that itself calls other bats returns
    control (matches the project release docs). Paths are normalized to native
    separators so ``call`` doesn't mistake a forward slash for a switch.
    """
    return ["cmd", "/c", "call", os.path.normpath(bat_path)]


def run_command(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
    """Run a command, streaming output; raise ReleaseCreateError on failure.

    In dry-run mode the command is only logged and never executed.
    """
    printable = " ".join(cmd)
    if dry_run:
        logger.info(f"[DRY RUN] Would run: {printable}")
        return

    logger.info(f"Running: {printable}")
    try:
        result = subprocess.run(cmd, cwd=cwd)
    except OSError as e:
        raise ReleaseCreateError(f"Failed to start command '{printable}': {e}") from e
    _raise_on_failure(result.returncode, printable)


def capture_command(cmd: list[str], cwd: Path) -> str:
    """Run a read-only command and return its trimmed stdout.

    Used for the version/build lookups needed to compute the label — it always
    runs (even under dry-run) because reading state changes nothing.
    """
    printable = " ".join(cmd)
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        raise ReleaseCreateError(f"Failed to start command '{printable}': {e}") from e
    _raise_on_failure(result.returncode, printable, result.stderr.strip())
    return result.stdout.strip()


def _raise_on_failure(returncode: int, printable: str, stderr: str = "") -> None:
    """Raise ReleaseCreateError for a non-zero exit, appending stderr if present."""
    if returncode != 0:
        detail = f"\n{stderr}" if stderr else ""
        raise ReleaseCreateError(
            f"Command failed (exit {returncode}): {printable}{detail}"
        )
