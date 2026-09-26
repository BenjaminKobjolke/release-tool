"""Tests for download-page version sidecars."""

import json
from pathlib import Path

from release_tool.version_file import AppVersion
from release_tool.version_sidecar import sidecar_payload, write_sidecar


def test_payload_includes_name_and_build() -> None:
    assert sidecar_payload(AppVersion(name="1.2.3", build=7)) == {
        "version": "1.2.3",
        "version_code": 7,
    }


def test_payload_without_name_contains_only_build() -> None:
    assert sidecar_payload(AppVersion(name="", build=38)) == {"version_code": 38}


def test_write_sidecar_uses_remote_filename(tmp_path: Path) -> None:
    path = write_sidecar(tmp_path, "tickets.apk", AppVersion(name="1.2.3", build=7))

    assert path == tmp_path / "tickets.apk.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": "1.2.3",
        "version_code": 7,
    }
