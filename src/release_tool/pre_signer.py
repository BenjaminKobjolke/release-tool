"""Pre-release signing workflow."""

import logging
import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .authenticode import read_signer_name
from .exceptions import PreSignError

logger = logging.getLogger(__name__)

# Copy-back retry: the local exe can be briefly locked (antivirus scan /
# lingering handle) right after signing. Retry over the transient lock.
_COPY_RETRIES = 5
_COPY_RETRY_DELAY = 2


class PreSignMethod(Enum):
    """Available pre-signing workflows."""

    NETWORK = "network"
    REMOTE = "remote"


@dataclass
class PreSignConfig:
    """Configuration for pre-signing process."""

    enabled: bool
    expected_signer: str
    method: PreSignMethod = PreSignMethod.NETWORK
    network_path: str = ""
    network_path_signed: str = ""
    signer_dir: str = ""
    poll_interval: int = 10
    timeout: int = 300


class PreSigner:
    """Handles pre-release signing workflow."""

    def __init__(self, config: PreSignConfig) -> None:
        self.config = config

    def process(self, file_path: Path) -> Path:
        """Main entry point - copies file to network, waits for signature, moves back."""
        logger.info(f"Pre-signing: {file_path.name}")
        logger.debug(f"Network path: {self.config.network_path}")
        logger.debug(f"Network path signed: {self.config.network_path_signed}")
        logger.debug(f"Expected signer: {self.config.expected_signer}")

        network_file = self._copy_to_network(file_path)
        signed_file = self._wait_for_signature(file_path.name)
        self._move_back(signed_file, network_file, file_path)

        logger.info(f"Pre-signing complete: {file_path.name}")
        return file_path

    def log_dry_run(self, file_path: Path) -> None:
        """Describe the network-share signing steps without copying files."""
        logger.info(f"[DRY RUN] Would copy {file_path.name} to {self.config.network_path}")
        logger.info(
            f"[DRY RUN] Would wait for signed file at: {self.config.network_path_signed}"
        )
        logger.info(f"[DRY RUN] Expected signer: {self.config.expected_signer}")
        logger.info(
            f"[DRY RUN] Poll interval: {self.config.poll_interval}s, "
            f"timeout: {self.config.timeout}s"
        )
        logger.info("[DRY RUN] Would move signed file back to source location")

    def _copy_to_network(self, file_path: Path) -> Path:
        """Copy file to network path, return destination path."""
        network_path = Path(self.config.network_path)

        if not network_path.exists():
            raise PreSignError(f"Network path not accessible: {network_path}")

        dest_path = network_path / file_path.name
        logger.debug(f"Copying {file_path} to {dest_path}")

        try:
            shutil.copy2(file_path, dest_path)
        except OSError as e:
            raise PreSignError(f"Failed to copy file to network: {e}") from e

        logger.info(f"Copied to network path: {dest_path}")
        return dest_path

    def _wait_for_signature(self, filename: str) -> Path:
        """Poll signed directory until file appears with correct signature."""
        start_time = time.time()
        poll_count = 0

        signed_path = Path(self.config.network_path_signed)
        signed_file = signed_path / filename

        logger.info(
            f"Waiting for signed file at {signed_file} "
            f"(timeout: {self.config.timeout}s, poll interval: {self.config.poll_interval}s)"
        )

        while True:
            elapsed = time.time() - start_time
            if elapsed >= self.config.timeout:
                raise PreSignError(f"Timeout waiting for signature after {self.config.timeout}s")

            poll_count += 1
            remaining = int(self.config.timeout - elapsed)

            if not signed_file.exists():
                logger.info(
                    f"Waiting for signed file... ({remaining}s remaining, "
                    f"file not yet in signed directory)"
                )
                time.sleep(self.config.poll_interval)
                continue

            signer = read_signer_name(signed_file)
            logger.debug(f"Poll #{poll_count}: signer = {signer}")

            if signer and signer == self.config.expected_signer:
                logger.info(f"Signature verified: {signer}")
                return signed_file

            logger.info(
                f"Waiting for signature... ({remaining}s remaining, "
                f"current: {signer or 'unsigned'})"
            )
            time.sleep(self.config.poll_interval)

    def _move_back(
        self, signed_file: Path, unsigned_network_file: Path, original_path: Path
    ) -> None:
        """Copy signed file back over original, then clean up the server."""
        logger.debug(f"Moving {signed_file} back to {original_path}")

        # Copy signed file over original, retrying over transient locks
        # (avoids permission issues with unlink). Hard fail if it never clears.
        for attempt in range(1, _COPY_RETRIES + 1):
            try:
                shutil.copy2(signed_file, original_path)
                break
            except OSError as e:
                if attempt == _COPY_RETRIES:
                    raise PreSignError(f"Failed to copy signed file back: {e}") from e
                logger.warning(
                    f"Copy-back failed (attempt {attempt}/{_COPY_RETRIES}), "
                    f"file may be locked; retrying in {_COPY_RETRY_DELAY}s: {e}"
                )
                time.sleep(_COPY_RETRY_DELAY)

        logger.info(f"Moved signed file back to: {original_path}")

        # Best-effort cleanup of the network share: warn on failure, never abort.
        self._cleanup_server(signed_file, unsigned_network_file)

    def _cleanup_server(self, signed_file: Path, unsigned_network_file: Path) -> None:
        """Delete signed + unsigned copies from the network share, best-effort."""
        for path in (signed_file, unsigned_network_file):
            try:
                if path.exists():
                    path.unlink()
                    logger.debug(f"Removed file from server: {path}")
            except OSError as e:
                logger.warning(f"Failed to delete file from server {path}: {e}")
