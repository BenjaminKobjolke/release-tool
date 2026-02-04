"""Release workflow orchestration."""

import logging
from pathlib import Path

from .config import OldFilePolicy, ReleaseConfig
from .ftp_client import FTPClient
from .old_file_handler import create_handler
from .pre_signer import PreSigner
from .release_notes_uploader import ReleaseNotesUploader

logger = logging.getLogger(__name__)


class ReleaseManager:
    """Orchestrates the release workflow."""

    def __init__(
        self,
        config: ReleaseConfig,
        dry_run: bool = False,
        version: str | None = None,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.version = version
        self.client = FTPClient(config.ftp)
        self.old_file_handler = create_handler(config.old_file)
        self.pre_signer = PreSigner(config.pre_sign) if config.pre_sign else None

    def release(self, file_path: Path) -> bool:
        """Execute the release workflow."""
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return False

        filename = file_path.name
        logger.info(f"Starting release of {filename}")

        if self.dry_run:
            return self._dry_run_release(file_path)

        return self._execute_release(file_path)

    def _dry_run_release(self, file_path: Path) -> bool:
        """Preview release without making changes."""
        filename = file_path.name

        if self.pre_signer:
            logger.info("[DRY RUN] Pre-signing enabled")
            logger.info(
                f"[DRY RUN] Would copy {filename} to {self.config.pre_sign.network_path}"
            )
            logger.info(
                f"[DRY RUN] Would wait for signed file at: "
                f"{self.config.pre_sign.network_path_signed}"
            )
            logger.info(
                f"[DRY RUN] Expected signer: {self.config.pre_sign.expected_signer}"
            )
            logger.info(
                f"[DRY RUN] Poll interval: {self.config.pre_sign.poll_interval}s, "
                f"timeout: {self.config.pre_sign.timeout}s"
            )
            logger.info("[DRY RUN] Would move signed file back to source location")

        logger.info("[DRY RUN] Would connect to FTP server")
        logger.info(f"[DRY RUN] Host: {self.config.ftp.host}:{self.config.ftp.port}")
        logger.info(f"[DRY RUN] Remote path: {self.config.ftp.remote_path}")
        logger.info(f"[DRY RUN] Would check if {filename} exists on remote")
        logger.info(
            f"[DRY RUN] Old file policy: {self.config.old_file.policy.value}"
        )
        if self.version:
            logger.info(f"[DRY RUN] Version for backup: {self.version}")
        logger.info(f"[DRY RUN] Would upload {file_path}")

        if self.config.release_notes:
            uploader = ReleaseNotesUploader(
                config=self.config.release_notes,
                client=self.client,
                dry_run=True,
            )
            uploader.upload()

        logger.info("[DRY RUN] Would disconnect from FTP server")
        return True

    def _check_version_exists(self) -> bool:
        """Check if version backup folder exists and prompt user.

        Returns True if should proceed, False if user aborted.
        """
        if not self.version:
            return True
        if self.config.old_file.policy != OldFilePolicy.RENAME:
            return True

        version_path = f"{self.config.old_file.subfolder_base}/{self.version}"

        with self.client.connection():
            if self.client.directory_exists(version_path):
                logger.warning(f"Version folder already exists: {version_path}")
                response = input(f"Version {self.version} already exists. Overwrite? [y/N]: ")
                if response.lower() != 'y':
                    logger.info("Aborted by user")
                    return False

        return True

    def _execute_release(self, file_path: Path) -> bool:
        """Execute the actual release."""
        filename = file_path.name

        # Check version existence BEFORE pre-signing
        if not self._check_version_exists():
            return False

        if self.pre_signer:
            logger.info("Starting pre-signing process...")
            file_path = self.pre_signer.process(file_path)

        with self.client.connection():
            logger.debug(f"Checking if file exists on remote: {filename}")
            if self.client.file_exists(filename):
                logger.info(f"Existing file found: {filename}")
                logger.debug(
                    f"Calling old file handler: {type(self.old_file_handler).__name__}"
                )
                logger.debug(f"Version parameter: {self.version}")
                self.old_file_handler.handle(self.client, filename, self.version)
            else:
                logger.debug(f"No existing file found on remote: {filename}")

            self.client.upload_file(file_path)
            logger.info(f"Successfully released {filename}")

            # Upload release notes if configured
            if self.config.release_notes:
                uploader = ReleaseNotesUploader(
                    config=self.config.release_notes,
                    client=self.client,
                    dry_run=False,
                )
                uploader.upload()

        return True
