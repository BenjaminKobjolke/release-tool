"""Pre-release signing workflow."""

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .exceptions import PreSignError

logger = logging.getLogger(__name__)


@dataclass
class PreSignConfig:
    """Configuration for pre-signing process."""

    enabled: bool
    network_path: str
    network_path_signed: str
    expected_signer: str
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

    def _get_signature(self, file_path: Path) -> str | None:
        """Get digital signature signer name using PowerShell."""
        cmd = [
            "powershell",
            "-Command",
            f"(Get-AuthenticodeSignature '{file_path}').SignerCertificate.Subject",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("PowerShell signature check timed out")
            return None
        except OSError as e:
            logger.warning(f"Failed to run PowerShell: {e}")
            return None

        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Parse CN= from subject string
        # Example: "CN=XIDA GmbH, O=XIDA GmbH, L=City, S=State, C=DE"
        subject = result.stdout.strip()
        for part in subject.split(","):
            part = part.strip()
            if part.startswith("CN="):
                return part[3:].strip()

        return None

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
                raise PreSignError(
                    f"Timeout waiting for signature after {self.config.timeout}s"
                )

            poll_count += 1
            remaining = int(self.config.timeout - elapsed)

            if not signed_file.exists():
                logger.info(
                    f"Waiting for signed file... ({remaining}s remaining, "
                    f"file not yet in signed directory)"
                )
                time.sleep(self.config.poll_interval)
                continue

            signer = self._get_signature(signed_file)
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
        """Move signed file back to original location and clean up."""
        logger.debug(f"Moving {signed_file} back to {original_path}")

        try:
            # Copy signed file over original (avoids permission issues with unlink)
            shutil.copy2(signed_file, original_path)
            # Remove the signed file from signed directory
            signed_file.unlink()
            logger.debug(f"Removed signed file from: {signed_file}")
            # Remove the original unsigned file from network path
            if unsigned_network_file.exists():
                unsigned_network_file.unlink()
                logger.debug(f"Removed unsigned file from: {unsigned_network_file}")
        except OSError as e:
            raise PreSignError(f"Failed to move signed file back: {e}") from e

        logger.info(f"Moved signed file back to: {original_path}")
