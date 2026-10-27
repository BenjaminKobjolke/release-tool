"""Resolve conflicts when the next release label is already tagged."""

import logging
from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path

from .bat_runner import find_existing_tag
from .cli_support import confirm
from .exceptions import ReleaseCreateError

logger = logging.getLogger(__name__)


class TagConflict(Enum):
    """How release creation should respond to an already-used shipping label."""

    STOP = auto()
    ASK = auto()
    AUTO = auto()


def conflict_mode(
    *, dry_run: bool, build_self_contained: bool, bump_if_tagged: bool, yes: bool
) -> TagConflict:
    """Select the tag-conflict policy, keeping non-mutating runs from bumping versions."""
    if dry_run or build_self_contained:
        return TagConflict.STOP
    if bump_if_tagged:
        return TagConflict.AUTO
    if yes:
        return TagConflict.STOP
    return TagConflict.ASK


def ensure_free_label(
    label: str,
    cwd: Path,
    mode: TagConflict,
    catch_up: Callable[[], str],
    *,
    confirm_fn: Callable[[str], bool] = confirm,
) -> str:
    """Return a free label, prompting or catching up according to ``mode``."""
    while (location := find_existing_tag(label, cwd)) is not None:
        message = f"Release tag {label} already exists {location}."
        if mode is TagConflict.STOP:
            raise ReleaseCreateError(
                f"{message} The version source is behind the last release; refusing to continue."
            )
        if mode is TagConflict.ASK and not confirm_fn(
            f"{message} Increment the version to the next free release label?"
        ):
            raise ReleaseCreateError(f"{message} Release creation stopped.")

        next_label = catch_up()
        if next_label == label:
            raise ReleaseCreateError(
                f"Incrementing the version did not change the shipping label {label}; stopping."
            )
        label = next_label
        logger.info("Next release label: %s", label)

    return label
