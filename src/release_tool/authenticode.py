"""Read the signer name from a Windows Authenticode signature."""

import subprocess
from pathlib import Path

from .mac_tools import AppLogger

logger = AppLogger(__name__)


def read_signer_name(file_path: Path) -> str | None:
    """Return the certificate common name, or None when the file is unsigned."""
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

    subject = result.stdout.strip()
    for part in subject.split(","):
        part = part.strip()
        if part.startswith("CN="):
            return part[3:].strip()

    return None
