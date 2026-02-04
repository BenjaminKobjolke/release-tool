"""Handlers for managing existing files on remote."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from .config import OldFileConfig, OldFilePolicy, SubfolderNaming
from .ftp_client import FTPClient

logger = logging.getLogger(__name__)


class OldFileHandler(ABC):
    """Abstract base class for old file handling strategies."""

    @abstractmethod
    def handle(self, client: FTPClient, filename: str, version: str | None) -> None:
        """Handle an existing file on remote."""


class DeleteHandler(OldFileHandler):
    """Handler that deletes existing files."""

    def handle(self, client: FTPClient, filename: str, version: str | None) -> None:
        """Delete the existing file."""
        client.delete_file(filename)
        logger.info(f"Deleted old file: {filename}")


class RenameHandler(OldFileHandler):
    """Handler that moves existing files to a backup subfolder."""

    def __init__(self, subfolder_base: str, naming: SubfolderNaming) -> None:
        self.subfolder_base = subfolder_base
        self.naming = naming

    def handle(self, client: FTPClient, filename: str, version: str | None) -> None:
        """Move the existing file to a backup subfolder."""
        logger.debug(
            f"RenameHandler.handle called: filename={filename}, version={version}"
        )
        logger.debug(
            f"Settings: subfolder_base={self.subfolder_base}, naming={self.naming}"
        )

        if self.naming == SubfolderNaming.TIMESTAMP:
            suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        else:
            if not version:
                suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
                logger.warning("No version provided, falling back to timestamp naming")
            else:
                suffix = version

        logger.debug(f"Computed suffix: {suffix}")
        subfolder = f"{self.subfolder_base}/{suffix}"
        logger.debug(f"Target subfolder path: {subfolder}")

        logger.debug(f"Creating base directory: {self.subfolder_base}")
        client.ensure_directory(self.subfolder_base)
        logger.debug(f"Creating version subfolder: {subfolder}")
        client.ensure_directory(subfolder)

        new_path = f"{subfolder}/{filename}"
        logger.debug(f"Renaming {filename} to {new_path}")
        client.rename_file(filename, new_path)
        logger.info(f"Moved old file to: {new_path}")


def create_handler(config: OldFileConfig) -> OldFileHandler:
    """Factory function to create the appropriate handler."""
    if config.policy == OldFilePolicy.DELETE:
        return DeleteHandler()
    else:
        return RenameHandler(config.subfolder_base, config.subfolder_naming)
