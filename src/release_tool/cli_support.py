"""Shared CLI plumbing: logging setup and the exception-to-exit-code contract.

Lives apart from ``cli`` so every subcommand module can import it without a
circular import back through the dispatcher.
"""

import logging
from collections.abc import Callable

from .exceptions import ConfigurationError, FTPError, ReleaseToolError


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
