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


def bump_last_segment(version: str, patch_max: int | None = None) -> str:
    """Increment the final dotted segment, rolling it over when a maximum is set."""
    parts = version.split(".")
    try:
        last = int(parts[-1])
    except ValueError as e:
        raise ReleaseCreateError(
            f"version_get returned a non-numeric last segment: {version!r}"
        ) from e
    if patch_max is not None and last + 1 > patch_max and len(parts) > 1:
        try:
            parts[-2] = str(int(parts[-2]) + 1)
        except ValueError as e:
            raise ReleaseCreateError(
                f"version_get returned a non-numeric second-to-last segment: {version!r}"
            ) from e
        parts[-1] = "0"
    else:
        parts[-1] = str(last + 1)
    return ".".join(parts)
