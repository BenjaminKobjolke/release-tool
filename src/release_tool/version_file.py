"""Reading and bumping the build number in a project's version file."""

import logging
import re
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

    ``pattern`` must expose a ``build`` group and — where the format carries a
    version name — a ``name`` group. The trailing lookahead
    keeps the line ending out of the match so a splice never rewrites it.
    """

    pattern: re.Pattern[str]


VERSION_FORMATS: dict[str, VersionFormat] = {
    # Flutter: version: 1.0.0+490
    "pubspec": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)version:[ \t]*(?P<name>\S+?)\+(?P<build>\d+)[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
    ),
    # Gradle Kotlin DSL: versionCode = 1
    "gradle_kts": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)versionCode\b[ \t]*=[ \t]*(?P<build>\d+)[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
    ),
    # Gradle Groovy: versionCode 201 (no '='; \b keeps versionCodeOverride out)
    "gradle_groovy": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)versionCode\b[ \t]+(?P<build>\d+)[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
    ),
    # Gradle version catalog: versionCode = "38"
    "toml": VersionFormat(
        pattern=re.compile(
            r"^(?P<indent>[ \t]*)versionCode\b[ \t]*=[ \t]*\"(?P<build>\d+)\"[ \t]*(?=\r?$)",
            re.MULTILINE,
        ),
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
    supporting a new project type means adding a pattern. The pattern must
    expose ``build``, plus ``name`` if that format carries a version name.

    The build number is written by `bump`; `set_name` writes the Flutter version
    name for create's optional version-name bump.

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
        self._write(new, text, matches)
        logger.info(f"Build number: {old.label} -> {new.label}")
        return old, new

    def set_name(self, name: str) -> tuple[AppVersion, AppVersion]:
        """Set the version name in place, preserving the build number."""
        old, text, matches = self._parse()
        if not old.name:
            raise ConfigurationError(f"Version file has no version name: {self.path}")
        new = AppVersion(name=name, build=old.build)
        self._write(new, text, matches)
        logger.info(f"Version name: {old.label} -> {new.label}")
        return old, new

    def _write(self, new: AppVersion, text: str, matches: list[re.Match[str]]) -> None:
        """Splice version fields without changing spacing or line endings."""
        # Work backwards so each replacement leaves earlier offsets valid.
        for match in reversed(matches):
            # An unchanged build keeps its own spelling: a name-only write must
            # not normalise `+01359` to `+1359`.
            if int(match.group("build")) != new.build:
                start, end = match.span("build")
                text = f"{text[:start]}{new.build}{text[end:]}"
            if "name" in match.groupdict():
                start, end = match.span("name")
                text = f"{text[:start]}{new.name}{text[end:]}"

        # newline="" so the file's own CRLF/LF survive the rewrite untouched.
        with self.path.open("w", encoding="utf-8", newline="") as f:
            f.write(text)

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
