"""Tests for release label and version-name calculations."""

import pytest

from release_tool.exceptions import ReleaseCreateError
from release_tool.release_labels import bump_last_segment


@pytest.mark.parametrize(
    ("version", "patch_max", "expected"),
    [
        ("1.7.9", None, "1.7.10"),
        ("1.7.9", 10, "1.7.10"),
        ("1.7.10", 10, "1.8.0"),
        ("1.7.13", 10, "1.8.0"),
        ("7", 6, "8"),
    ],
)
def test_bump_last_segment(version: str, patch_max: int | None, expected: str) -> None:
    assert bump_last_segment(version, patch_max) == expected


def test_bump_last_segment_rejects_non_numeric_second_to_last_on_rollover() -> None:
    with pytest.raises(ReleaseCreateError, match="second-to-last segment"):
        bump_last_segment("1.x.10", 10)
