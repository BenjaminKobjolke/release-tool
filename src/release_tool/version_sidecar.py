"""Write the `<download>.json` consumed by the app downloads webpage."""

import json
from pathlib import Path

from .version_file import AppVersion

SIDECAR_SUFFIX = ".json"


def sidecar_filename(remote_filename: str) -> str:
    """The `<remote>.json` name, shared by the local write and the remote upload."""
    return f"{remote_filename}{SIDECAR_SUFFIX}"


def sidecar_payload(version: AppVersion) -> dict[str, str | int]:
    """Return the download-page metadata for one app version."""
    payload: dict[str, str | int] = {"version_code": version.build}
    if version.name:
        payload = {"version": version.name, **payload}
    return payload


def write_sidecar(directory: Path, remote_filename: str, version: AppVersion) -> Path:
    """Write and return the sidecar path next to the built artifact."""
    path = directory / sidecar_filename(remote_filename)
    path.write_text(json.dumps(sidecar_payload(version), indent=2), encoding="utf-8")
    return path
