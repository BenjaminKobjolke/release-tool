"""Render GitHub release notes from XIDA's JSON format."""

import json
from pathlib import Path

from .exceptions import GitHubReleaseError


def render_notes_markdown(en_json_path: Path) -> str:
    """Render an XIDA release-notes ``en.json`` (``title`` + ``notes: [...]``) as markdown."""
    if not en_json_path.exists():
        raise GitHubReleaseError(f"Release notes file not found: {en_json_path}")

    try:
        data = json.loads(en_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GitHubReleaseError(
            f"Failed to read release notes {en_json_path}: {error}"
        ) from error

    title = data.get("title")
    notes = data.get("notes")
    if not isinstance(title, str) or not isinstance(notes, list):
        raise GitHubReleaseError(
            f"{en_json_path} must have a string 'title' and a list 'notes'"
        )

    lines = [f"# {title}", ""]
    lines.extend(f"- {item}" for item in notes)
    return "\n".join(lines) + "\n"
