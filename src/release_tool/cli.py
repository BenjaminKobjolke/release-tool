"""Command-line interface for release tool."""

import argparse
import logging
import sys
from pathlib import Path

from .config import ReleaseConfig
from .exceptions import ConfigurationError, FTPError, ReleaseToolError
from .release_manager import ReleaseManager


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="release-tool",
        description="Release software via FTP",
    )

    parser.add_argument(
        "file",
        type=Path,
        help="Path to file to upload",
    )

    parser.add_argument(
        "config",
        type=Path,
        help="Path to configuration file",
    )

    parser.add_argument(
        "--previous-version",
        "-p",
        dest="version",
        help="Previous version string for backup folder naming (e.g., '1.0.0')",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without uploading",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args(args)


def run(args: argparse.Namespace) -> int:
    """Execute the release based on parsed arguments."""
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        config = ReleaseConfig.from_ini_file(args.config)
        manager = ReleaseManager(
            config=config,
            dry_run=args.dry_run,
            version=args.version,
        )

        if manager.release(args.file):
            return 0
        return 1

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        return 2

    except FTPError as e:
        logger.error(f"FTP error: {e}")
        return 3

    except ReleaseToolError as e:
        logger.error(f"Error: {e}")
        return 1

    except KeyboardInterrupt:
        logger.info("Operation cancelled")
        return 130


def main(args: list[str] | None = None) -> int:
    """Main entry point."""
    parsed_args = parse_args(args)
    return run(parsed_args)


if __name__ == "__main__":
    sys.exit(main())
