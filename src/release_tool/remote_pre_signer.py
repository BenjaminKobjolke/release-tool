"""Run the SafeNet signer client as a remote pre-signing workflow."""

import os
import subprocess
from pathlib import Path

from .authenticode import read_signer_name
from .bat_runner import bat_command
from .exceptions import PreSignError
from .mac_tools import AppLogger
from .pre_signer import PreSignConfig

logger = AppLogger(__name__)

SIGN_BAT = "sign.bat"
NO_PAUSE_ENV = "SIGNER_NO_PAUSE"
EXIT_CODE_MEANINGS = {
    1: "check the signer's config.json; mode must be client",
    2: "the signing server reported that signing failed",
    3: "timed out waiting for the signed file; check timeout in the signer's config.json",
    4: "connection or transfer error with the signing server",
}


class RemotePreSigner:
    """Run a local signer client and verify the returned file's certificate."""

    def __init__(self, config: PreSignConfig) -> None:
        self.config = config

    def process(self, file_path: Path) -> Path:
        """Run sign.bat, stream its progress and verify its in-place result."""
        signer_dir = Path(self.config.signer_dir).resolve()
        signer_bat = signer_dir / SIGN_BAT
        if not signer_bat.is_file():
            raise PreSignError(f"Remote signer not found: {signer_bat}")

        absolute_file = file_path.resolve()
        command = bat_command(str(signer_bat)) + [str(absolute_file)]
        environment = os.environ.copy()
        environment[NO_PAUSE_ENV] = "1"

        try:
            process = subprocess.Popen(
                command,
                cwd=signer_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
        except OSError as e:
            raise PreSignError(f"Failed to start remote signer {signer_bat}: {e}") from e

        if process.stdout is not None:
            for line in process.stdout:
                progress = line.rstrip("\r\n")
                if progress:
                    logger.info(f"Signer: {progress}")
            process.stdout.close()

        return_code = process.wait()
        if return_code != 0:
            meaning = EXIT_CODE_MEANINGS.get(return_code, "unexpected exit code")
            raise PreSignError(
                f"Remote signing failed with exit code {return_code}: {meaning}"
            )

        signer = read_signer_name(absolute_file)
        if signer != self.config.expected_signer:
            raise PreSignError(
                f"Remote signing signature mismatch: expected '{self.config.expected_signer}', "
                f"got '{signer or 'unsigned'}'"
            )

        logger.info(f"Signature verified: {signer}")
        return file_path

    def log_dry_run(self, file_path: Path) -> None:
        """Describe the client command without starting it."""
        signer_dir = Path(self.config.signer_dir).resolve()
        command = bat_command(str(signer_dir / SIGN_BAT)) + [str(file_path.resolve())]
        logger.info(f"[DRY RUN] Would set {NO_PAUSE_ENV}=1")
        logger.info(f"[DRY RUN] Would run: {' '.join(command)}")
        logger.info(f"[DRY RUN] Expected signer: {self.config.expected_signer}")
