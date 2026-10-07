"""Labels and version-name increments for full releases."""

from dataclasses import dataclass

from .exceptions import ReleaseCreateError


@dataclass(frozen=True)
class VersionNameBump:
    """The version name before and after this release."""

    old: str
    new: str


@dataclass(frozen=True)
class ReleaseLabels:
    """Previous, shipping and notes labels derived from one version read."""

    previous: str
    shipping: str
    notes: str
    name_bump: VersionNameBump | None = None


def bump_last_segment(version: str) -> str:
    """Increment the final dotted numeric segment of a version name."""
    parts = version.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except ValueError as e:
        raise ReleaseCreateError(
            f"version_get returned a non-numeric last segment: {version!r}"
        ) from e
    return ".".join(parts)
