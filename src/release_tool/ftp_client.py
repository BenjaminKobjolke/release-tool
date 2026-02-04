"""FTP client for release operations."""

import contextlib
import ftplib
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .config import FTPConfig
from .exceptions import FTPError

logger = logging.getLogger(__name__)


class FTPClient:
    """FTP client for release operations."""

    def __init__(self, config: FTPConfig) -> None:
        self.config = config
        self._ftp: ftplib.FTP | None = None

    def connect(self) -> None:
        """Establish FTP connection and navigate to remote path."""
        try:
            self._ftp = ftplib.FTP()
            self._ftp.connect(self.config.host, self.config.port)
            self._ftp.login(self.config.username, self.config.password)

            if self.config.remote_path and self.config.remote_path != "/":
                logger.debug(f"Changing to remote path: {self.config.remote_path}")
                try:
                    self._ftp.cwd(self.config.remote_path)
                except ftplib.error_perm:
                    logger.debug(f"Remote path doesn't exist, creating: {self.config.remote_path}")
                    self._create_remote_path(self.config.remote_path)
                    self._ftp.cwd(self.config.remote_path)

            cwd = self._ftp.pwd()
            logger.info(f"Connected to FTP server: {self.config.host}:{self.config.port}")
            logger.debug(f"Current working directory: {cwd}")

        except (ftplib.Error, OSError, EOFError) as e:
            raise FTPError(f"Failed to connect to FTP server: {e}") from e

    def disconnect(self) -> None:
        """Close FTP connection gracefully."""
        if self._ftp:
            try:
                self._ftp.quit()
            except (ftplib.Error, OSError, EOFError):
                with contextlib.suppress(Exception):
                    self._ftp.close()
            self._ftp = None
            logger.info("Disconnected from FTP server")

    @contextmanager
    def connection(self) -> Generator["FTPClient", None, None]:
        """Context manager for auto-connect/disconnect."""
        self.connect()
        try:
            yield self
        finally:
            self.disconnect()

    def _create_remote_path(self, path: str) -> None:
        """Create remote directory path recursively."""
        if not self._ftp:
            raise FTPError("Not connected to FTP server")

        dirs = path.strip("/").split("/")
        current_dir = ""

        for directory in dirs:
            current_dir = f"{current_dir}/{directory}" if current_dir else directory
            try:
                self._ftp.mkd(current_dir)
                logger.debug(f"Created directory: {current_dir}")
            except ftplib.error_perm:
                pass

    def file_exists(self, filename: str) -> bool:
        """Check if file exists on remote."""
        if not self._ftp:
            raise FTPError("Not connected to FTP server")

        try:
            self._ftp.voidcmd("TYPE I")  # Switch to binary mode for SIZE command
            size = self._ftp.size(filename)
            logger.debug(f"File exists: {filename} (size: {size} bytes)")
            return True
        except ftplib.error_perm as e:
            logger.debug(f"File does not exist: {filename} (error: {e})")
            return False

    def delete_file(self, filename: str) -> None:
        """Delete a file on remote."""
        if not self._ftp:
            raise FTPError("Not connected to FTP server")

        try:
            self._ftp.delete(filename)
            logger.info(f"Deleted remote file: {filename}")
        except ftplib.error_perm as e:
            raise FTPError(f"Failed to delete file {filename}: {e}") from e

    def rename_file(self, old_name: str, new_name: str) -> None:
        """Rename or move a file on remote."""
        if not self._ftp:
            raise FTPError("Not connected to FTP server")

        logger.debug(f"rename_file: {old_name} -> {new_name}")
        try:
            self._ftp.rename(old_name, new_name)
            logger.info(f"Renamed {old_name} to {new_name}")
        except ftplib.error_perm as e:
            logger.debug(f"Rename failed: {e}")
            raise FTPError(f"Failed to rename {old_name} to {new_name}: {e}") from e

    def ensure_directory(self, path: str) -> None:
        """Create directory path recursively if it doesn't exist."""
        if not self._ftp:
            raise FTPError("Not connected to FTP server")

        logger.debug(f"ensure_directory called with path: {path}")
        dirs = path.strip("/").split("/")
        logger.debug(f"Path components: {dirs}")
        current_dir = ""

        for directory in dirs:
            current_dir = f"{current_dir}/{directory}" if current_dir else directory
            try:
                self._ftp.mkd(current_dir)
                logger.debug(f"Created directory: {current_dir}")
            except ftplib.error_perm as e:
                logger.debug(f"Directory already exists or error: {current_dir} ({e})")

    def upload_file(self, local_path: Path) -> str:
        """Upload a file to the current remote directory."""
        if not self._ftp:
            raise FTPError("Not connected to FTP server")

        filename = local_path.name
        logger.debug(f"Uploading file: {local_path} -> {filename}")

        try:
            with open(local_path, "rb") as f:
                self._ftp.storbinary(f"STOR {filename}", f)
            logger.info(f"Uploaded {filename}")
            return filename
        except (ftplib.Error, OSError, EOFError) as e:
            logger.debug(f"Upload failed: {e}")
            raise FTPError(f"Failed to upload {filename}: {e}") from e
