"""CLI entry point for checking configured FTP profiles."""

import argparse
import logging
from pathlib import Path

from .cli_support import guarded, setup_logging
from .config import PROFILES_FILE
from .ftp_check import DEFAULT_TIMEOUT_SECONDS, check_profiles


def parse_check_ftp_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the check-ftp subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool check-ftp",
        description="Check every configured FTP profile without changing the server",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=PROFILES_FILE,
        help="Path to the FTP profiles INI (default: ftp_profiles.ini in the release-tool checkout)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Connection timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_check_ftp(args: list[str]) -> int:
    """Check all FTP profiles and return a status reflecting the results."""
    parsed = parse_check_ftp_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        results = check_profiles(parsed.profiles, parsed.timeout)
        for result in results:
            if result.ok:
                logger.info(f"OK   {result.name}: {result.detail}")
            else:
                logger.error(f"FAIL {result.name}: {result.detail}")
        successful = sum(result.ok for result in results)
        logger.info(f"{successful} of {len(results)} FTP profiles OK")
        return all(result.ok for result in results)

    return guarded(logger, action)
