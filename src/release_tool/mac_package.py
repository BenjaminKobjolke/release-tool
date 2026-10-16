"""Build a signed, notarized, and verified macOS installer package."""

import logging
import shutil
import tempfile
from pathlib import Path

from .bat_runner import run_command
from .exceptions import MacPackageError
from .mac_config import MacPackageConfig
from .mac_tools import (
    ASSESS,
    CODESIGN,
    ENTITLEMENTS,
    FORCE,
    OPTIONS_RUNTIME,
    SIGN,
    SPCTL,
    STAPLE,
    STAPLER,
    TIMESTAMP,
    TYPE,
    XCRUN,
    notarize,
    require_macos,
)

logger = logging.getLogger(__name__)

PKGBUILD = "pkgbuild"
PKGUTIL = "pkgutil"
ROOT = "--root"
INSTALL_LOCATION = "--install-location"
SCRIPTS = "--scripts"
IDENTIFIER = "--identifier"
VERSION = "--version"
CHECK_SIGNATURE = "--check-signature"
INSTALL = "install"
VERBOSE = "--verbose"


class MacPackager:
    """Run Apple's signing and installer tools for one binary."""

    def __init__(self, config: MacPackageConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run

    def package(self, binary: Path) -> Path:
        """Sign, package, notarize, staple, and verify the configured binary."""
        if not binary.is_file():
            raise MacPackageError(f"Binary not found: {binary}")
        require_macos("mac-package", self.dry_run)

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
        notarize(self.config.output, self.config.keychain_profile, cwd, self.dry_run)

    def _finish_and_verify(self, cwd: Path) -> None:
        """Staple Apple's ticket and check the final installer signature and policy."""
        commands = (
            [XCRUN, STAPLER, STAPLE, str(self.config.output)],
            [PKGUTIL, CHECK_SIGNATURE, str(self.config.output)],
            [SPCTL, ASSESS, TYPE, INSTALL, VERBOSE, str(self.config.output)],
        )
        for command in commands:
            run_command(command, cwd=cwd, dry_run=self.dry_run)
