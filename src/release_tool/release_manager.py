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

    def release(self, file_path: Path, remote_filename: str | None = None) -> bool:
        """Execute the release workflow with an optional one-release remote name."""
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return False

        remote_name = self._remote_name(file_path, remote_filename)
        logger.info(f"Starting release of {file_path.name} as {remote_name}")

        if self.dry_run:
            return self._dry_run_release(file_path, remote_name)

        return self._execute_release(file_path, remote_name)

    def _remote_name(self, file_path: Path, override: str | None) -> str:
        """The name the file gets on the server — override, configured, else local."""
        return override or self.config.ftp.remote_filename or file_path.name

    def _dry_run_release(self, file_path: Path, remote_name: str) -> bool:
        """Preview release without making changes."""
        # Pre-signing works on the local file; everything after it names the remote one.
        pre_sign = self.config.pre_sign
        if pre_sign:
            logger.info("[DRY RUN] Pre-signing enabled")
            logger.info(f"[DRY RUN] Would copy {file_path.name} to {pre_sign.network_path}")
            logger.info(f"[DRY RUN] Would wait for signed file at: {pre_sign.network_path_signed}")
            logger.info(f"[DRY RUN] Expected signer: {pre_sign.expected_signer}")
            logger.info(
                f"[DRY RUN] Poll interval: {pre_sign.poll_interval}s, timeout: {pre_sign.timeout}s"
            )
            logger.info("[DRY RUN] Would move signed file back to source location")

        logger.info("[DRY RUN] Would connect to FTP server")
        logger.info(f"[DRY RUN] Host: {self.config.ftp.host}:{self.config.ftp.port}")
        logger.info(f"[DRY RUN] Remote path: {self.config.ftp.remote_path}")
        logger.info(f"[DRY RUN] Would check if {remote_name} exists on remote")
        logger.info(f"[DRY RUN] Old file policy: {self.config.old_file.policy.value}")
        if self.version:
            logger.info(f"[DRY RUN] Version for backup: {self.version}")
        logger.info(f"[DRY RUN] Would upload {file_path} as {remote_name}")

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
                if response.lower() != "y":
                    logger.info("Aborted by user")
                    return False

        return True

    def _execute_release(self, file_path: Path, remote_name: str) -> bool:
        """Execute the actual release."""
        # Check version existence BEFORE pre-signing
        if not self._check_version_exists():
            return False

        if self.pre_signer:
            logger.info("Starting pre-signing process...")
            file_path = self.pre_signer.process(file_path)

        with self.client.connection():
            logger.debug(f"Checking if file exists on remote: {remote_name}")
            if self.client.file_exists(remote_name):
                logger.info(f"Existing file found: {remote_name}")
                logger.debug(f"Calling old file handler: {type(self.old_file_handler).__name__}")
                logger.debug(f"Version parameter: {self.version}")
                self.old_file_handler.handle(self.client, remote_name, self.version)
            else:
                logger.debug(f"No existing file found on remote: {remote_name}")

            self.client.upload_file(file_path, remote_name)
            logger.info(f"Successfully released {remote_name}")

            # Upload release notes if configured
            if self.config.release_notes:
                uploader = ReleaseNotesUploader(
                    config=self.config.release_notes,
                    client=self.client,
                    dry_run=False,
                )
                uploader.upload()

        return True
