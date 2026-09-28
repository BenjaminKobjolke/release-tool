"""Shared CLI plumbing: logging, prompts, and exception-to-exit-code handling.

Lives apart from ``cli`` so every subcommand module can import it without a
circular import back through the dispatcher.
"""

import logging
import os
from collections.abc import Callable

from .exceptions import ConfigurationError, FTPError, ReleaseToolError

WATCHER_ENV_VAR = "TICKETS_WATCHER_COMMAND_RUN"
WATCHER_INPUT_MARKER = "::tw-input-line::"


def confirm(prompt: str) -> bool:
    """Ask a y/N question and return True only for ``y``."""
    if os.environ.get(WATCHER_ENV_VAR) == "1":
        # Protocol output must reach stdout directly before input blocks.
        print(WATCHER_INPUT_MARKER, flush=True)
    return input(f"{prompt}: ").strip().lower() == "y"


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def guarded(logger: logging.Logger, action: Callable[[], bool]) -> int:
    """Run a CLI action, mapping tool exceptions to exit codes.

    Shared by every entry point so the exception→exit-code contract cannot drift.
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
