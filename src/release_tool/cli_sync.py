"""CLI entry point for the `sync` subcommand."""

import argparse
import logging
from pathlib import Path

from .cli_support import guarded, setup_logging
from .directory_sync import DirectorySync
from .ftp_client import FTPClient
from .sync_config import SyncConfig


def parse_sync_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the `sync` subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool sync",
        description="Upload a local directory tree to an FTP remote",
    )
    parser.add_argument("config", type=Path, help="Path to the sync config INI")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root local_dir resolves against (default: cwd)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the files that would be uploaded without connecting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_sync(args: list[str]) -> int:
    """Execute the `sync` (directory upload) workflow."""
    parsed = parse_sync_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        config = SyncConfig.from_ini_file(parsed.config)
        return DirectorySync(
            config=config,
            project_root=(parsed.project_root or Path.cwd()).resolve(),
            client=FTPClient(config.ftp),
            dry_run=parsed.dry_run,
        ).sync()

    return guarded(logger, action)
