"""CLI entry point for building a macOS installer package."""

import argparse
import logging
from pathlib import Path

from .cli_support import guarded, setup_logging
from .mac_config import MacPackageConfig
from .mac_package import MacPackager


def parse_mac_package_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the `mac-package` subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool mac-package",
        description="Sign, notarize, and verify a macOS installer package",
    )
    parser.add_argument("binary", type=Path, help="Path to the raw executable")
    parser.add_argument("config", type=Path, help="Path to the mac-package config INI")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root all configured paths resolve against (default: cwd)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log commands without running them")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(args)


def run_mac_package(args: list[str]) -> int:
    """Execute the `mac-package` workflow."""
    parsed = parse_mac_package_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        project_root = parsed.project_root.resolve()
        config = MacPackageConfig.from_ini_file(parsed.config, project_root)
        binary = parsed.binary if parsed.binary.is_absolute() else project_root / parsed.binary
        MacPackager(config, dry_run=parsed.dry_run).package(binary.resolve())
        return True

    return guarded(logger, action)
