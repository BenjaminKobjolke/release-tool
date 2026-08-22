"""Command-line interface for release tool."""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from .config import ReleaseConfig
from .create_config import CreateConfig
from .exceptions import ConfigurationError, FTPError, ReleaseToolError
from .github_publisher import GitHubPublisher, GitHubReleaseConfig, render_notes_markdown
from .release_creator import ReleaseCreator
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


def _guarded(logger: logging.Logger, action: Callable[[], bool]) -> int:
    """Run a CLI action, mapping tool exceptions to exit codes.

    Shared by both entry points so the exception→exit-code contract cannot drift.
    """
    try:
        return 0 if action() else 1
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


def run(args: argparse.Namespace) -> int:
    """Execute the release based on parsed arguments."""
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        config = ReleaseConfig.from_ini_file(args.config)
        manager = ReleaseManager(
            config=config,
            dry_run=args.dry_run,
            version=args.version,
        )
        return manager.release(args.file)

    return _guarded(logger, action)


def parse_create_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the `create` subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool create",
        description="Create a full release (label, notes, build, publish, tag)",
    )
    parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        default=Path("release_create.ini"),
        help="Path to the create config INI (default: release_create.ini in the cwd)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root the bats/notes resolve against (default: cwd)",
    )
    parser.add_argument(
        "--internal",
        action="store_true",
        help="Internal test build: skip release notes, tag as INTERNAL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the resolved label and commands without executing",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_create(args: list[str]) -> int:
    """Execute the `create` (full-release) workflow."""
    parsed = parse_create_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        config = CreateConfig.from_ini_file(parsed.config)
        creator = ReleaseCreator(
            config=config,
            project_root=(parsed.project_root or Path.cwd()).resolve(),
            dry_run=parsed.dry_run,
        )
        return creator.create(internal=parsed.internal)

    return _guarded(logger, action)


def parse_github_release_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the `github-release` subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool github-release",
        description="Create a GitHub Release for a tag and attach assets",
    )
    parser.add_argument("tag", help="Git tag the release attaches to (e.g. v1.7.5)")
    parser.add_argument("assets", nargs="*", type=Path, help="Asset files to attach")
    parser.add_argument(
        "--repo",
        help="OWNER/NAME. Required unless the cwd's git remote resolves the repo.",
    )
    parser.add_argument("--title", help="Release title (default: the tag)")
    notes_group = parser.add_mutually_exclusive_group()
    notes_group.add_argument("--notes", help="Release notes as literal text")
    notes_group.add_argument("--notes-file", type=Path, help="Path to a markdown notes file")
    notes_group.add_argument(
        "--notes-json", type=Path, help="XIDA release-notes en.json to render as markdown"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the gh command without running it",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_github_release(args: list[str]) -> int:
    """Execute the `github-release` (publish-a-release) workflow."""
    parsed = parse_github_release_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        notes = render_notes_markdown(parsed.notes_json) if parsed.notes_json else parsed.notes
        config = GitHubReleaseConfig(enabled=True, repo=parsed.repo)
        GitHubPublisher(config).publish(
            parsed.tag,
            parsed.assets,
            title=parsed.title,
            notes=notes,
            notes_file=parsed.notes_file,
            dry_run=parsed.dry_run,
        )
        return True

    return _guarded(logger, action)


def main(args: list[str] | None = None) -> int:
    """Main entry point."""
    argv = sys.argv[1:] if args is None else args
    if argv and argv[0] == "create":
        return run_create(argv[1:])
    if argv and argv[0] == "github-release":
        return run_github_release(argv[1:])

    parsed_args = parse_args(args)
    return run(parsed_args)


if __name__ == "__main__":
    sys.exit(main())
