"""Release notes upload functionality."""

import logging
from pathlib import Path

from .config import ReleaseNotesConfig
from .ftp_client import FTPClient

logger = logging.getLogger(__name__)


class ReleaseNotesUploader:
    """Uploads new release notes folders to FTP."""

    def __init__(
        self,
        config: ReleaseNotesConfig,
        client: FTPClient,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.client = client
        self.dry_run = dry_run

    def upload(self) -> bool:
        """Upload new release notes folders.

        Returns True on success, False on failure.
        """
        local_path = Path(self.config.path)

        if not local_path.exists():
            logger.error(f"Release notes path not found: {local_path}")
            return False

        if not local_path.is_dir():
            logger.error(f"Release notes path is not a directory: {local_path}")
            return False

        # Get local version folders
        local_folders = self._get_local_folders(local_path)
        if not local_folders:
            logger.info("No release notes folders found locally")
            return True

        if self.dry_run:
            return self._dry_run_upload(local_path, local_folders)

        return self._execute_upload(local_path, local_folders)

    def _get_local_folders(self, local_path: Path) -> list[str]:
        """Get list of version folder names from local path."""
        folders = []
        for item in local_path.iterdir():
            if item.is_dir():
                folders.append(item.name)
        folders.sort()
        logger.debug(f"Local release notes folders: {folders}")
        return folders

    def _get_remote_folders(self) -> list[str]:
        """Get list of version folder names from remote path."""
        try:
            self.client.change_directory(self.config.remote_path)
            folders = self.client.list_directories()
            logger.debug(f"Remote release notes folders: {folders}")
            return folders
        except Exception as e:
            logger.debug(f"Could not list remote folders: {e}")
            return []

    def _dry_run_upload(self, local_path: Path, local_folders: list[str]) -> bool:
        """Preview upload without making changes."""
        logger.info("[DRY RUN] Release notes upload:")
        logger.info(f"[DRY RUN] Local path: {local_path}")
        logger.info(f"[DRY RUN] Remote path: {self.config.remote_path}")
        logger.info(f"[DRY RUN] Local folders: {local_folders}")
        logger.info("[DRY RUN] Would check remote for existing folders")
        logger.info("[DRY RUN] Would upload new folders")
        return True

    def _execute_upload(self, local_path: Path, local_folders: list[str]) -> bool:
        """Execute the actual upload."""
        # Ensure remote path exists
        self.client.ensure_directory(self.config.remote_path)

        # Get existing remote folders
        remote_folders = self._get_remote_folders()

        # Find new folders
        new_folders = [f for f in local_folders if f not in remote_folders]

        if not new_folders:
            logger.info("No new release notes folders to upload")
            return True

        logger.info(f"New release notes folders to upload: {new_folders}")

        for folder_name in new_folders:
            local_folder = local_path / folder_name
            remote_folder = f"{self.config.remote_path}/{folder_name}"

            logger.info(f"Uploading release notes folder: {folder_name}")

            # Create folder on remote
            self.client.ensure_directory(remote_folder)
            self.client.change_directory(remote_folder)

            # Upload all files in the folder
            for file_path in local_folder.iterdir():
                if file_path.is_file():
                    self.client.upload_file(file_path)

        logger.info("Release notes upload complete")
        return True
