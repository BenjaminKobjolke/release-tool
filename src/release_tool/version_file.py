"""Reading and bumping the build number in a project's version file."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)

DEFAULT_VERSION_FILE = "pubspec.yaml"
DEFAULT_VERSION_FORMAT = "pubspec"

MIN_BUILD_NUMBER = 1


@dataclass(frozen=True)
class AppVersion:
    """The version a build ships under: an optional name plus the build number."""

    name: str
    build: int

    @property
    def label(self) -> str:
        """`1.0.0+490` where a name exists, else just the build number."""
        return f"{self.name}+{self.build}" if self.name else str(self.build)


@dataclass(frozen=True)
class VersionFormat:
    """How one project type spells its version line.

    ``pattern`` must expose a ``build`` group, an ``indent`` group, and — where
    the format carries a version name — a ``name`` group. The trailing lookahead
    keeps the line ending out of the match so a splice never rewrites it.
    """

    pattern: re.Pattern[str]
    render: Callable[[str, AppVersion], str]


VERSION_FORMATS: dict[str, VersionFormat] = {
    # Flutter: version: 1.0.0+490
    "pubspec": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)version:[ \t]*(?P<name>\S+?)\+(?P<build>\d+)[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
        render=lambda indent, version: f"{indent}version: {version.name}+{version.build}",
    ),
    # Gradle Kotlin DSL: versionCode = 1
    "gradle_kts": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)versionCode\b[ \t]*=[ \t]*(?P<build>\d+)[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
        render=lambda indent, version: f"{indent}versionCode = {version.build}",
    ),
    # Gradle Groovy: versionCode 201 (no '='; \b keeps versionCodeOverride out)
    "gradle_groovy": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)versionCode\b[ \t]+(?P<build>\d+)[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
        render=lambda indent, version: f"{indent}versionCode {version.build}",
    ),
    # Gradle version catalog: versionCode = "38"
    "toml": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)versionCode\b[ \t]*=[ \t]*\"(?P<build>\d+)\"[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
        render=lambda indent, version: f'{indent}versionCode = "{version.build}"',
    ),
}


def validate_version_format(raw: str) -> str:
    """Return the format name, or raise naming the valid ones.

    Shared so config parsing can reject a typo before a build runs, without
    restating the rule the VersionFile constructor already enforces.
    """
    if raw not in VERSION_FORMATS:
        raise ConfigurationError(
            f"Invalid version file format: {raw}. "
            f"Valid formats: {', '.join(sorted(VERSION_FORMATS))}"
        )
    return raw


class VersionFile:
    """Reads and rewrites the build number in a project's version file.

    One splice implementation over a table of formats (``VERSION_FORMATS``), so
    supporting a new project type means adding a pattern and a render function —
    no subclass, no factory. The pattern must expose ``indent`` and ``build``
    groups, plus ``name`` if that format carries a version name.

    Only the build number is ever written. A semver name (Flutter's `version:`,
    Gradle's `versionName`) is edited by hand.

    A file may declare the build number more than once — monocles_chat sets
    `versionCode` in both `defaultConfig` and a product flavor. Every occurrence
    is rewritten together, and occurrences that disagree are an error rather than
    a guess about which one wins.
    """

    def __init__(self, path: Path, version_format: str = DEFAULT_VERSION_FORMAT) -> None:
        self.path = path
        self.format = VERSION_FORMATS[validate_version_format(version_format)]

    def read(self) -> AppVersion:
        """Parse the current version, or raise if the file has no usable version line."""
        version, _, _ = self._parse()
        return version

    def bump(self, step: int = 1) -> tuple[AppVersion, AppVersion]:
        """Add `step` to the build number in place. Returns (old, new)."""
        old, text, matches = self._parse()
        new_build = old.build + step
        if new_build < MIN_BUILD_NUMBER:
            raise ConfigurationError(
                f"Refusing to set the build number below {MIN_BUILD_NUMBER}: "
                f"{old.label} with step {step} in {self.path}"
            )

        new = AppVersion(name=old.name, build=new_build)
        # Splice from the end so each replacement leaves earlier offsets valid.
        for match in reversed(matches):
            start, end = match.span()
            line = self.format.render(match.group("indent"), new)
            text = f"{text[:start]}{line}{text[end:]}"

        # newline="" so the file's own CRLF/LF survive the rewrite untouched.
        with self.path.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
        logger.info(f"Build number: {old.label} -> {new.label}")
        return old, new

    def _parse(self) -> tuple[AppVersion, str, list[re.Match[str]]]:
        """Return the parsed version, the raw file text, and every matching line."""
        if not self.path.exists():
            raise ConfigurationError(f"Version file not found: {self.path}")

        with self.path.open(encoding="utf-8", newline="") as f:
            text = f.read()

        matches = list(self.format.pattern.finditer(text))
        if not matches:
            raise ConfigurationError(
                f"No version line found in {self.path} for the configured format. "
                "Check [Build] version_file and version_file_format."
            )

        builds = {int(match.group("build")) for match in matches}
        if len(builds) > 1:
            lines = sorted(text.count("\n", 0, match.start()) + 1 for match in matches)
            raise ConfigurationError(
                f"Version numbers disagree in {self.path}: found {sorted(builds)} "
                f"on lines {lines}. Make them equal before bumping."
            )

        first = matches[0]
        name = first.group("name") if "name" in first.groupdict() else ""
        return AppVersion(name=name or "", build=builds.pop()), text, matches
