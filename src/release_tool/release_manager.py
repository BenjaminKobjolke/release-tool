"""Release workflow orchestration."""

import logging
from pathlib import Path

from .config import ReleaseConfig
from .ftp_client import FTPClient
from .old_file_handler import create_handler

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
        logger.info("[DRY RUN] Would disconnect from FTP server")
        return True

    def _execute_release(self, file_path: Path) -> bool:
        """Execute the actual release."""
        filename = file_path.name

        with self.client.connection():
            if self.client.file_exists(filename):
                logger.info(f"Existing file found: {filename}")
                self.old_file_handler.handle(self.client, filename, self.version)

            self.client.upload_file(file_path)
            logger.info(f"Successfully released {filename}")

        return True
