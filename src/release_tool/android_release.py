"""Orchestration for the `android` command: bump, build, verify, upload."""

import logging
from datetime import datetime
from pathlib import Path

from .android_config import AndroidConfig, BuildVariant
from .bat_runner import run_command
from .exceptions import FTPError, ReleaseCreateError
from .ftp_client import FTPClient
from .release_manager import ReleaseManager
from .version_file import AppVersion, VersionFile
from .version_sidecar import (
    SIDECAR_SUFFIX,
    sidecar_filename,
    sidecar_payload,
    write_sidecar,
)

logger = logging.getLogger(__name__)


class AndroidReleaseRunner:
    """Builds an Android APK and publishes it under a fixed name on the server.

    Replaces the per-project bat chains (build number bump + `fvm flutter build apk`
    + rclone `copyto`). Collaborators are injected so each step can be substituted
    in tests and so the class's dependencies are visible in its signature.
    """

    def __init__(
        self,
        config: AndroidConfig,
        project_root: Path,
        release_manager: ReleaseManager,
        ftp_client: FTPClient,
        version_file: VersionFile,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.release_manager = release_manager
        self.ftp_client = ftp_client
        self.version_file = version_file
        self.dry_run = dry_run

    def release(self, debug: bool = False) -> bool:
        """Run the full build-and-upload for one variant."""
        variant = self.config.variant(debug)
        apk = self.project_root / variant.apk

        version = self._bump(variant)
        try:
            self._build(variant, apk)
        except Exception:
            self._roll_back(variant)
            raise

        uploaded = self._upload(variant, apk)
        if uploaded:
            self._upload_sidecar(variant, apk, version)
            self._log_summary(variant, apk, version.label)
        return uploaded

    def _bump(self, variant: BuildVariant) -> AppVersion:
        """Advance the build number if this variant bumps; return the shipping version."""
        if not variant.bump:
            return self.version_file.read()
        if self.dry_run:
            current = self.version_file.read()
            logger.info(f"[DRY RUN] Would bump the build number from {current.label}")
            return current

        _, new = self.version_file.bump()
        return new

    def _build(self, variant: BuildVariant, apk: Path) -> None:
        """Build the APK, then prove the build actually produced it."""
        # Delete only the artifact we verify — a whole-directory wipe would also
        # destroy the other variant's APK, since both land in the same folder.
        if not self.dry_run and apk.exists():
            logger.debug(f"Deleting stale APK: {apk}")
            apk.unlink()

        run_command(variant.command, cwd=self.project_root, dry_run=self.dry_run)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would verify {apk}")
            return
        if not apk.exists():
            raise ReleaseCreateError(f"APK not found after the build: {apk}")

    def _roll_back(self, variant: BuildVariant) -> None:
        """Undo the bump after a failed build, without hiding why it failed."""
        if not variant.bump or self.dry_run:
            return
        try:
            self.version_file.bump(-1)
        except Exception as e:
            logger.error(f"Failed to roll back the build number: {e}")

    def _upload(self, variant: BuildVariant, apk: Path) -> bool:
        """Publish the APK, or narrate the upload in a dry run."""
        if self.dry_run:
            ftp = self.config.release.ftp
            logger.info(
                f"[DRY RUN] Would upload {apk} to "
                f"{ftp.host}:{ftp.port}{ftp.remote_path}{variant.remote_filename}"
            )
            return True

        return self.release_manager.release(apk)

    def _upload_sidecar(
        self, variant: BuildVariant, apk: Path, version: AppVersion
    ) -> None:
        """Publish the metadata file only after its APK is online."""
        name = sidecar_filename(variant.remote_filename)
        if self.dry_run:
            logger.info(f"[DRY RUN] Would upload {name}: {sidecar_payload(version)}")
            return

        path = write_sidecar(apk.parent, variant.remote_filename, version)
        try:
            with self.ftp_client.connection():
                self.ftp_client.upload_file(path, name)
        except FTPError as e:
            raise FTPError(f"APK uploaded, but the version file {name} failed: {e}") from e

        if variant.public_url:
            logger.info(f"Uploaded version file to: {variant.public_url}{SIDECAR_SUFFIX}")

    def _log_summary(self, variant: BuildVariant, apk: Path, label: str) -> None:
        """Report what shipped — the mtime catches an accidentally stale APK."""
        logger.info(f"Version: {label}")
        if not self.dry_run:
            modified = datetime.fromtimestamp(apk.stat().st_mtime)
            logger.info(f"Last modified: {modified:%Y-%m-%d %H:%M:%S}")
        if variant.public_url:
            logger.info(f"Uploaded to: {variant.public_url}")
