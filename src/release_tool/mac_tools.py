"""Shared Apple command-line pieces for the mac commands."""

import json
import logging
import sys
from pathlib import Path

from .bat_runner import capture_command, run_command
from .exceptions import MacPackageError, ReleaseToolError


class AppLogger:
    """Route macOS signing messages through the application's logging backend."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def debug(self, message: str, *args: object) -> None:
        self._logger.debug(message, *args)

    def info(self, message: str, *args: object) -> None:
        self._logger.info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        self._logger.warning(message, *args)

    def error(self, message: str, *args: object) -> None:
        self._logger.error(message, *args)

CODESIGN = "codesign"
XCRUN = "xcrun"
SPCTL = "spctl"
FORCE = "--force"
OPTIONS_RUNTIME = "--options=runtime"
ENTITLEMENTS = "--entitlements"
SIGN = "--sign"
TIMESTAMP = "--timestamp"
NOTARYTOOL = "notarytool"
SUBMIT = "submit"
KEYCHAIN_PROFILE = "--keychain-profile"
WAIT = "--wait"
OUTPUT_FORMAT_JSON = "--output-format"
JSON = "json"
STAPLER = "stapler"
STAPLE = "staple"
ASSESS = "--assess"
TYPE = "--type"
NOTARIZATION_HINT = "xcrun notarytool log {id} --keychain-profile {profile}"
LOG = "log"
VALIDATE = "validate"
ACCEPTED = "Accepted"


def require_macos(command_name: str, dry_run: bool) -> None:
    """Reject real Apple-tool runs on other platforms."""
    if not dry_run and sys.platform != "darwin":
        raise MacPackageError(
            f"{command_name} needs macOS: codesign and xcrun come with the Xcode "
            f"Command Line Tools (running on {sys.platform})"
        )


def notarize(path: Path, profile: str, cwd: Path, dry_run: bool) -> None:
    """Submit one artifact and require Apple's accepted status."""
    command = [
        XCRUN,
        NOTARYTOOL,
        SUBMIT,
        str(path),
        KEYCHAIN_PROFILE,
        profile,
        WAIT,
        OUTPUT_FORMAT_JSON,
        JSON,
    ]
    AppLogger(__name__).info("Submitting for Apple notarization; this can take several minutes.")
    if dry_run:
        run_command(command, cwd=cwd, dry_run=True)
        return
    check_notarization(capture_command(command, cwd=cwd), profile, cwd)


def check_notarization(stdout: str, profile: str, cwd: Path) -> None:
    """Reject malformed or non-accepted responses and log Apple's issue details."""
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise MacPackageError(f"Unable to parse notarytool response: {error}") from error
    if isinstance(result, dict) and result.get("status") == ACCEPTED:
        return

    submission_id = result.get("id", "unknown") if isinstance(result, dict) else "unknown"
    hint = NOTARIZATION_HINT.format(id=submission_id, profile=profile)
    if submission_id and submission_id != "unknown":
        try:
            details = capture_command(
                [XCRUN, NOTARYTOOL, LOG, str(submission_id), KEYCHAIN_PROFILE, profile], cwd=cwd
            )
            AppLogger(__name__).error(
                "Notarization issues for submission %s:\n%s", submission_id, details
            )
        except ReleaseToolError as error:
            AppLogger(__name__).warning(
                "Unable to fetch notarization issues for %s: %s", submission_id, error
            )
    raise MacPackageError(
        f"Apple notarization was not accepted (submission {submission_id}). "
        f"Inspect the result with: {hint}"
    )
