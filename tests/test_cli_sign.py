"""Tests for the sign subcommand."""

from pathlib import Path

import pytest

from release_tool.cli import main

PROFILES = """[remote]
enabled = true
method = remote
signer_dir = signer
expected_signer = Example Corp

[off]
enabled = false
"""


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, Path]:
    profiles = tmp_path / "signing_profiles.ini"
    profiles.write_text(PROFILES, encoding="utf-8")
    exe = tmp_path / "dummy.exe"
    exe.write_bytes(b"MZ")
    return exe, profiles


def test_signs_file_with_profile(setup: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    exe, profiles = setup
    signed: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        "release_tool.remote_pre_signer.RemotePreSigner.process",
        lambda self, path: signed.append((self.config.expected_signer, path)) or path,
    )

    assert main(["sign", str(exe), "remote", "--profiles", str(profiles)]) == 0
    assert signed == [("Example Corp", exe)]


def test_unknown_profile_is_configuration_error(setup: tuple[Path, Path]) -> None:
    exe, profiles = setup
    assert main(["sign", str(exe), "typo", "--profiles", str(profiles)]) == 2


def test_disabled_profile_is_configuration_error(setup: tuple[Path, Path]) -> None:
    exe, profiles = setup
    assert main(["sign", str(exe), "off", "--profiles", str(profiles)]) == 2


def test_missing_file_is_configuration_error(setup: tuple[Path, Path]) -> None:
    exe, profiles = setup
    missing = exe.with_name("nope.exe")
    assert main(["sign", str(missing), "remote", "--profiles", str(profiles)]) == 2
