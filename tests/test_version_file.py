"""Tests for the version file reader/writer."""

from pathlib import Path

import pytest

from release_tool.exceptions import ConfigurationError
from release_tool.version_file import AppVersion, VersionFile

# One real snippet per supported format, copied from the projects that use it.
FORMAT_CASES = [
    # (format, version line, build number, surrounding indent context)
    ("pubspec", "version: 1.0.0+490", 490),
    ("gradle_kts", "        versionCode = 1", 1),
    ("gradle_groovy", "        versionCode 201", 201),
    ("toml", 'versionCode = "38"', 38),
]


def write_file(path: Path, version_line: str, eol: str = "\n") -> None:
    """Write a small file with the given version line and line endings."""
    # Digit-free filler: the byte-level assertions below rewrite the build number
    # everywhere it appears, so surrounding numbers would create false matches.
    lines = ["before = alpha", version_line, "", "after = omega"]
    path.write_bytes(eol.join(lines).encode("utf-8") + eol.encode("utf-8"))


class TestAppVersion:
    """Tests for the AppVersion value object."""

    def test_label_with_name(self) -> None:
        """Flutter versions carry a semver name."""
        assert AppVersion(name="1.0.0", build=490).label == "1.0.0+490"

    def test_label_without_name(self) -> None:
        """Gradle formats only bump versionCode, so the label is the build alone."""
        assert AppVersion(name="", build=38).label == "38"

    def test_is_frozen(self) -> None:
        """The value object must not be mutable."""
        version = AppVersion(name="1.0.0", build=1)
        with pytest.raises(AttributeError):
            version.build = 2  # type: ignore[misc]


class TestFormats:
    """Every supported format reads, bumps and round-trips."""

    @pytest.mark.parametrize(("fmt", "line", "build"), FORMAT_CASES)
    def test_reads_build(self, tmp_path: Path, fmt: str, line: str, build: int) -> None:
        """The build number is parsed out of each syntax."""
        path = tmp_path / "version_file"
        write_file(path, line)

        assert VersionFile(path, fmt).read().build == build

    @pytest.mark.parametrize(("fmt", "line", "build"), FORMAT_CASES)
    def test_bump_rewrites_only_the_number(
        self, tmp_path: Path, fmt: str, line: str, build: int
    ) -> None:
        """Indentation, quoting and the rest of the file survive the splice."""
        path = tmp_path / "version_file"
        write_file(path, line)
        original = path.read_bytes()

        old, new = VersionFile(path, fmt).bump()

        assert (old.build, new.build) == (build, build + 1)
        expected = original.replace(str(build).encode(), str(build + 1).encode())
        assert path.read_bytes() == expected

    @pytest.mark.parametrize(("fmt", "line", "build"), FORMAT_CASES)
    @pytest.mark.parametrize("eol", ["\n", "\r\n"])
    def test_round_trip_is_byte_identical(
        self, tmp_path: Path, fmt: str, line: str, build: int, eol: str
    ) -> None:
        """bump then decrement restores the file exactly, LF and CRLF alike."""
        path = tmp_path / "version_file"
        write_file(path, line, eol=eol)
        original = path.read_bytes()

        version_file = VersionFile(path, fmt)
        version_file.bump()
        version_file.bump(-1)

        assert path.read_bytes() == original

    def test_unknown_format_raises(self, tmp_path: Path) -> None:
        """A typo'd format must name the valid ones."""
        with pytest.raises(ConfigurationError, match="pubspec"):
            VersionFile(tmp_path / "f", "gradle")

    def test_pubspec_keeps_the_version_name(self, tmp_path: Path) -> None:
        """Only the build is bumped; the semver name is edited by hand."""
        path = tmp_path / "pubspec.yaml"
        write_file(path, "version: 1.2.3+9")

        _, new = VersionFile(path, "pubspec").bump()

        assert new.label == "1.2.3+10"

    def test_groovy_ignores_version_code_override(self, tmp_path: Path) -> None:
        """`versionCodeOverride` and bare reads must not be mistaken for the setting."""
        path = tmp_path / "build.gradle"
        path.write_text(
            "        versionCode 201\n"
            "        output.versionCodeOverride = (100 * "
            "project.android.defaultConfig.versionCode) + baseAbiVersionCode\n",
            encoding="utf-8",
        )

        VersionFile(path, "gradle_groovy").bump()

        text = path.read_text(encoding="utf-8")
        assert "versionCode 202" in text
        assert "(100 * project.android.defaultConfig.versionCode)" in text


class TestMultipleOccurrences:
    """monocles_chat declares versionCode twice — both must move together."""

    def test_agreeing_occurrences_all_bump(self, tmp_path: Path) -> None:
        """A defaultConfig and a product flavor holding the same number stay in step."""
        path = tmp_path / "build.gradle"
        path.write_text(
            '        versionCode 201\n        versionName "2.1.5"\n'
            '            versionCode 201\n            versionName "2.1.5"\n',
            encoding="utf-8",
        )

        _, new = VersionFile(path, "gradle_groovy").bump()

        assert new.build == 202
        assert path.read_text(encoding="utf-8").count("versionCode 202") == 2

    def test_disagreeing_occurrences_raise(self, tmp_path: Path) -> None:
        """Guessing which one is authoritative would ship an inconsistent build."""
        path = tmp_path / "build.gradle"
        path.write_text("        versionCode 201\n            versionCode 7\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="disagree"):
            VersionFile(path, "gradle_groovy").read()

    def test_disagreeing_occurrences_write_nothing(self, tmp_path: Path) -> None:
        """A rejected bump must leave the file untouched."""
        path = tmp_path / "build.gradle"
        path.write_text("        versionCode 201\n            versionCode 7\n", encoding="utf-8")
        original = path.read_bytes()

        with pytest.raises(ConfigurationError):
            VersionFile(path, "gradle_groovy").bump()

        assert path.read_bytes() == original


class TestSetName:
    @pytest.mark.parametrize("eol", ["\n", "\r\n"])
    def test_changes_only_name_and_round_trips(self, tmp_path: Path, eol: str) -> None:
        path = tmp_path / "pubspec.yaml"
        write_file(path, "  version: 1.1.0+1359", eol)
        original = path.read_bytes()
        version_file = VersionFile(path)

        old, new = version_file.set_name("1.1.1")

        assert (old.label, new.label) == ("1.1.0+1359", "1.1.1+1359")
        assert path.read_bytes() == original.replace(b"1.1.0", b"1.1.1")
        version_file.set_name("1.1.0")
        assert path.read_bytes() == original

    def test_leaves_a_leading_zero_build_token_alone(self, tmp_path: Path) -> None:
        """A name-only write must not normalise `+01359` to `+1359`."""
        path = tmp_path / "pubspec.yaml"
        write_file(path, "version: 1.1.0+01359")
        original = path.read_bytes()
        version_file = VersionFile(path)

        version_file.set_name("1.1.1")

        assert path.read_bytes() == original.replace(b"1.1.0", b"1.1.1")
        version_file.set_name("1.1.0")
        assert path.read_bytes() == original

    def test_format_without_name_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "build.gradle.kts"
        write_file(path, "versionCode = 9")
        original = path.read_bytes()

        with pytest.raises(ConfigurationError, match="version name"):
            VersionFile(path, "gradle_kts").set_name("1.1.1")

        assert path.read_bytes() == original

    def test_keeps_version_line_spacing_on_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "pubspec.yaml"
        write_file(path, "  version:   1.1.0+1359  ", "\r\n")
        original = path.read_bytes()
        version_file = VersionFile(path)

        version_file.bump()
        version_file.set_name("1.1.1")
        version_file.set_name("1.1.0")
        version_file.bump(-1)

        assert path.read_bytes() == original


class TestErrors:
    """Failure modes shared by every format."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """A missing version file is a configuration problem, not a crash."""
        with pytest.raises(ConfigurationError, match="not found"):
            VersionFile(tmp_path / "pubspec.yaml", "pubspec").read()

    def test_no_version_line_raises(self, tmp_path: Path) -> None:
        """A file without the expected line cannot be bumped."""
        path = tmp_path / "pubspec.yaml"
        path.write_text("name: app\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="version"):
            VersionFile(path, "pubspec").read()

    def test_pubspec_version_without_build_raises(self, tmp_path: Path) -> None:
        """`version: 1.0.0` has no build number to increment."""
        path = tmp_path / "pubspec.yaml"
        write_file(path, "version: 1.0.0")
        with pytest.raises(ConfigurationError, match="version"):
            VersionFile(path, "pubspec").read()

    def test_tolerates_trailing_whitespace(self, tmp_path: Path) -> None:
        """Trailing spaces after the number are not part of it."""
        path = tmp_path / "pubspec.yaml"
        write_file(path, "version: 1.2.3+9  ")
        assert VersionFile(path, "pubspec").read() == AppVersion(name="1.2.3", build=9)

    def test_refuses_to_go_below_one(self, tmp_path: Path) -> None:
        """Build numbers are positive; a rollback past 1 is a bug, not a value."""
        path = tmp_path / "pubspec.yaml"
        write_file(path, "version: 1.0.0+1")

        with pytest.raises(ConfigurationError, match="below 1"):
            VersionFile(path, "pubspec").bump(-1)

        assert "version: 1.0.0+1" in path.read_text(encoding="utf-8")
