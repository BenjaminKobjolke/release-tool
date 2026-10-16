"""Build a signed, notarized, and verified macOS installer package."""

import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from .bat_runner import capture_command, run_command
from .exceptions import MacPackageError
from .mac_config import MacPackageConfig

logger = logging.getLogger(__name__)

CODESIGN = "codesign"
PKGBUILD = "pkgbuild"
XCRUN = "xcrun"
PKGUTIL = "pkgutil"
SPCTL = "spctl"
FORCE = "--force"
OPTIONS_RUNTIME = "--options=runtime"
ENTITLEMENTS = "--entitlements"
SIGN = "--sign"
TIMESTAMP = "--timestamp"
ROOT = "--root"
INSTALL_LOCATION = "--install-location"
SCRIPTS = "--scripts"
IDENTIFIER = "--identifier"
VERSION = "--version"
NOTARYTOOL = "notarytool"
SUBMIT = "submit"
KEYCHAIN_PROFILE = "--keychain-profile"
WAIT = "--wait"
OUTPUT_FORMAT_JSON = "--output-format"
JSON = "json"
STAPLER = "stapler"
STAPLE = "staple"
CHECK_SIGNATURE = "--check-signature"
ASSESS = "--assess"
TYPE = "--type"
INSTALL = "install"
VERBOSE = "--verbose"
NOTARIZATION_HINT = "xcrun notarytool log {id} --keychain-profile {profile}"


class MacPackager:
    """Run Apple's signing and installer tools for one binary."""

    def __init__(self, config: MacPackageConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run

    def package(self, binary: Path) -> Path:
        """Sign, package, notarize, staple, and verify the configured binary."""
        if not binary.is_file():
            raise MacPackageError(f"Binary not found: {binary}")
        if not self.dry_run and sys.platform != "darwin":
            raise MacPackageError(
                "mac-package needs macOS: codesign, pkgbuild and xcrun come with the "
                f"Xcode Command Line Tools (running on {sys.platform})"
            )

        cwd = self.config.output.parent
        if not self.dry_run:
            cwd.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                CODESIGN,
                FORCE,
                OPTIONS_RUNTIME,
                ENTITLEMENTS,
                str(self.config.entitlements),
                SIGN,
                self.config.app_identity,
                TIMESTAMP,
                str(binary),
            ],
            cwd=cwd,
            dry_run=self.dry_run,
        )

        if not self.dry_run and self.config.output.exists():
            self.config.output.unlink()

        with tempfile.TemporaryDirectory(prefix="release-tool-mac-") as temp_dir:
            stage = Path(temp_dir)
            shutil.copy2(binary, stage / binary.name)
            self._build_package(stage, cwd)

        self._notarize(cwd)
        self._finish_and_verify(cwd)
        logger.info(f"Created macOS package: {self.config.output}")
        return self.config.output

    def _build_package(self, stage: Path, cwd: Path) -> None:
        """Wrap the single staged binary with the configured installer metadata."""
        command = [
            PKGBUILD,
            ROOT,
            str(stage),
            INSTALL_LOCATION,
            self.config.install_location,
        ]
        if self.config.scripts is not None:
            command.extend([SCRIPTS, str(self.config.scripts)])
        command.extend(
            [
                IDENTIFIER,
                self.config.identifier,
                VERSION,
                self.config.version,
                SIGN,
                self.config.installer_identity,
                str(self.config.output),
            ]
        )
        run_command(command, cwd=cwd, dry_run=self.dry_run)

    def _notarize(self, cwd: Path) -> None:
        """Submit the installer and require Apple's accepted status."""
        command = [
            XCRUN,
            NOTARYTOOL,
            SUBMIT,
            str(self.config.output),
            KEYCHAIN_PROFILE,
            self.config.keychain_profile,
            WAIT,
            OUTPUT_FORMAT_JSON,
            JSON,
        ]
        logger.info("Submitting package for Apple notarization; this can take several minutes.")
        if self.dry_run:
            run_command(command, cwd=cwd, dry_run=True)
            return
        check_notarization(capture_command(command, cwd=cwd), self.config.keychain_profile)

    def _finish_and_verify(self, cwd: Path) -> None:
        """Staple Apple's ticket and check the final installer signature and policy."""
        commands = (
            [XCRUN, STAPLER, STAPLE, str(self.config.output)],
            [PKGUTIL, CHECK_SIGNATURE, str(self.config.output)],
            [SPCTL, ASSESS, TYPE, INSTALL, VERBOSE, str(self.config.output)],
        )
        for command in commands:
            run_command(command, cwd=cwd, dry_run=self.dry_run)


def check_notarization(stdout: str, profile: str) -> None:
    """Reject malformed or non-accepted notarytool JSON responses."""
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise MacPackageError(f"Unable to parse notarytool response: {error}") from error
    if not isinstance(result, dict) or result.get("status") != "Accepted":
        submission_id = result.get("id", "unknown") if isinstance(result, dict) else "unknown"
        hint = NOTARIZATION_HINT.format(id=submission_id, profile=profile)
        raise MacPackageError(
            f"Apple notarization was not accepted (submission {submission_id}). "
            f"Inspect the result with: {hint}"
        )
