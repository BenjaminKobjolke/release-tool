"""Shared runner for external commands (batch files, git, codex).

Every ``.bat`` / git / codex call in the create workflow goes through here so
command execution, error handling, and dry-run behavior live in one place.
"""

import logging
import os
import shutil
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


def _resolve(cmd: list[str]) -> list[str]:
    """Resolve cmd[0] to a full path via PATH/PATHEXT.

    Windows CreateProcess doesn't apply PATHEXT, so bare ``codex`` (really
    ``codex.cmd``) fails with WinError 2. shutil.which honors PATHEXT; leave
    the argv untouched if nothing resolves so the original error still surfaces.
    """
    exe = shutil.which(cmd[0])
    return [exe, *cmd[1:]] if exe else cmd


def run_command(
    cmd: list[str], cwd: Path, dry_run: bool = False, close_stdin: bool = False
) -> None:
    """Run a command, streaming output; raise ReleaseCreateError on failure.

    In dry-run mode the command is only logged and never executed. Closing stdin
    prevents children such as Codex from waiting for EOF on an inherited pipe;
    batch files keep the pipe so their prompts remain answerable.
    """
    printable = " ".join(cmd)
    if dry_run:
        logger.info(f"[DRY RUN] Would run: {printable}")
        return

    logger.info(f"Running: {printable}")
    try:
        result = subprocess.run(
            _resolve(cmd), cwd=cwd, stdin=subprocess.DEVNULL if close_stdin else None
        )
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
        result = subprocess.run(_resolve(cmd), cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        raise ReleaseCreateError(f"Failed to start command '{printable}': {e}") from e
    _raise_on_failure(result.returncode, printable, result.stderr.strip())
    return result.stdout.strip()


def has_staged_changes(cwd: Path) -> bool:
    """Return whether the index differs from HEAD.

    ``git diff --cached --quiet`` exits 1 when staged changes exist, so that
    status is an answer here; any other non-zero exit remains an error.
    """
    cmd = ["git", "diff", "--cached", "--quiet"]
    printable = " ".join(cmd)
    try:
        result = subprocess.run(_resolve(cmd), cwd=cwd)
    except OSError as e:
        raise ReleaseCreateError(f"Failed to start command '{printable}': {e}") from e
    if result.returncode == 1:
        return True
    _raise_on_failure(result.returncode, printable)
    return False


def find_existing_tag(label: str, cwd: Path) -> str | None:
    """Return where a git tag exists, or ``None`` when neither checked location has it."""
    local_cmd = ["git", "rev-parse", "-q", "--verify", f"refs/tags/{label}"]
    local_printable = " ".join(local_cmd)
    try:
        local_result = subprocess.run(
            _resolve(local_cmd), cwd=cwd, capture_output=True, text=True
        )
    except OSError as e:
        raise ReleaseCreateError(
            f"Failed to start command '{local_printable}': {e}"
        ) from e
    if local_result.returncode == 0:
        return "locally"
    if local_result.returncode != 1:
        _raise_on_failure(local_result.returncode, local_printable, local_result.stderr.strip())

    remote_cmd = ["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{label}"]
    try:
        remote_result = subprocess.run(
            _resolve(remote_cmd), cwd=cwd, capture_output=True, text=True
        )
    except OSError as e:
        logger.warning("Could not check origin tags for %s: %s", label, e)
        return None
    if remote_result.returncode == 0:
        return "on origin"
    if remote_result.returncode == 2:
        return None

    detail = remote_result.stderr.strip()
    logger.warning(
        "Could not check origin tags for %s (exit %s)%s",
        label,
        remote_result.returncode,
        f": {detail}" if detail else "",
    )
    return None


def _raise_on_failure(returncode: int, printable: str, stderr: str = "") -> None:
    """Raise ReleaseCreateError for a non-zero exit, appending stderr if present."""
    if returncode != 0:
        detail = f"\n{stderr}" if stderr else ""
        raise ReleaseCreateError(f"Command failed (exit {returncode}): {printable}{detail}")
