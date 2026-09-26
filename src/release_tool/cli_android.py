"""CLI entry points for the `android` and `bump-build` subcommands."""

import argparse
import logging
from pathlib import Path

from .android_config import AndroidConfig
from .android_release import AndroidReleaseRunner
from .cli_support import guarded, setup_logging
from .ftp_client import FTPClient
from .release_manager import ReleaseManager
from .version_file import DEFAULT_VERSION_FORMAT, VERSION_FORMATS, VersionFile


def parse_android_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the `android` subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool android",
        description="Build an Android APK and upload it under a fixed name",
    )
    parser.add_argument("config", type=Path, help="Path to the android config INI")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root the build command and paths resolve against (default: cwd)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Build the debug variant (no build-number bump, uploads as <name>-debug)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the resolved build and upload without changing anything",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_android(args: list[str]) -> int:
    """Execute the `android` (build-and-upload) workflow."""
    parsed = parse_android_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        config = AndroidConfig.from_ini_file(parsed.config)
        project_root = (parsed.project_root or Path.cwd()).resolve()
        runner = AndroidReleaseRunner(
            config=config,
            project_root=project_root,
            release_manager=ReleaseManager(config=config.release, dry_run=parsed.dry_run),
            ftp_client=FTPClient(config.release.ftp),
            version_file=VersionFile(
                project_root / config.version_file, config.version_file_format
            ),
            dry_run=parsed.dry_run,
        )
        return runner.release(debug=parsed.debug)

    return guarded(logger, action)


def parse_bump_build_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the `bump-build` subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool bump-build",
        description="Increment (or decrement) the build number in a pubspec.yaml",
    )
    parser.add_argument("version_file", type=Path, help="Path to the pubspec.yaml")
    parser.add_argument(
        "--format",
        dest="version_format",
        choices=sorted(VERSION_FORMATS),
        default=DEFAULT_VERSION_FORMAT,
        help="Syntax of the version file (default: pubspec)",
    )
    parser.add_argument(
        "--decrement",
        action="store_true",
        help="Subtract one instead of adding one (rollback)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_bump_build(args: list[str]) -> int:
    """Execute the `bump-build` workflow."""
    parsed = parse_bump_build_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        VersionFile(parsed.version_file, parsed.version_format).bump(-1 if parsed.decrement else 1)
        return True

    return guarded(logger, action)
