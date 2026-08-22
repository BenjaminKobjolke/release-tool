"""GitHub Releases publishing.

Shells out to the ``gh`` CLI (the same convention as the PowerShell/git/codex
calls elsewhere in this project) so the package stays dependency-free — no
``requests``/``PyGithub``, ``gh`` owns auth via ``gh auth login``.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import GitHubReleaseError

logger = logging.getLogger(__name__)

_ALREADY_EXISTS_MARKER = "already exists"


@dataclass
class GitHubReleaseConfig:
    """Configuration for GitHub Releases publishing.

    ``assets``/``tag_format``/``title_format`` are only used by the `create`
    workflow gate (``release_creator._maybe_github_release``); the plain CLI
    subcommand takes assets/tag/title as explicit arguments instead and leaves
    these at their defaults.
    """

    enabled: bool
    repo: str | None = None
    assets: list[str] = field(default_factory=list)
    tag_format: str = "{label}"
    title_format: str = "{label}"


def render_notes_markdown(en_json_path: Path) -> str:
    """Render an XIDA release-notes ``en.json`` (``title`` + ``notes: [...]``) as markdown."""
    if not en_json_path.exists():
        raise GitHubReleaseError(f"Release notes file not found: {en_json_path}")

    try:
        data = json.loads(en_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise GitHubReleaseError(f"Failed to read release notes {en_json_path}: {e}") from e

    title = data.get("title")
    notes = data.get("notes")
    if not isinstance(title, str) or not isinstance(notes, list):
        raise GitHubReleaseError(
            f"{en_json_path} must have a string 'title' and a list 'notes'"
        )

    lines = [f"# {title}", ""]
    lines.extend(f"- {item}" for item in notes)
    return "\n".join(lines) + "\n"


class GitHubPublisher:
    """Creates (or updates) a GitHub Release for a pushed tag via the ``gh`` CLI."""

    def __init__(self, config: GitHubReleaseConfig) -> None:
        self.config = config

    def publish(
        self,
        tag: str,
        assets: list[Path],
        *,
        title: str | None = None,
        notes: str | None = None,
        notes_file: Path | None = None,
        cwd: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        """Create the GitHub Release for ``tag`` and attach ``assets``.

        ``cwd`` matters: ``gh`` infers the target repo from the git remote of its
        working directory. Callers running from an unrelated cwd must pass
        ``self.config.repo`` (via ``--repo``) instead of relying on inference.
        """
        if shutil.which("gh") is None:
            raise GitHubReleaseError(
                "gh CLI not found on PATH. Install it and run 'gh auth login'."
            )

        for asset in assets:
            if not asset.exists():
                raise GitHubReleaseError(f"Asset not found: {asset}")

        cleanup_notes_file: Path | None = None
        try:
            if notes is not None and notes_file is None:
                notes_file = cleanup_notes_file = self._write_temp_notes(notes)

            argv = self._build_create_argv(tag, assets, title=title, notes_file=notes_file)

            if dry_run:
                logger.info(f"[DRY RUN] Would run: {' '.join(str(a) for a in argv)}")
                return

            logger.info(f"Creating GitHub Release {tag}")
            result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"GitHub Release {tag} created.")
                return

            if _ALREADY_EXISTS_MARKER in result.stderr.lower():
                logger.info(f"Release {tag} already exists; uploading assets instead.")
                self._upload_assets(tag, assets, cwd=cwd)
                return

            raise GitHubReleaseError(f"gh release create failed: {self._last_line(result.stderr)}")
        finally:
            if cleanup_notes_file is not None:
                cleanup_notes_file.unlink(missing_ok=True)

    def _build_create_argv(
        self,
        tag: str,
        assets: list[Path],
        *,
        title: str | None,
        notes_file: Path | None,
    ) -> list[str]:
        argv = ["gh", "release", "create", tag, *[str(a) for a in assets]]
        argv += ["--title", title or tag]
        if notes_file is not None:
            argv += ["--notes-file", str(notes_file)]
        else:
            argv += ["--generate-notes"]
        if self.config.repo:
            argv += ["--repo", self.config.repo]
        return argv

    def _upload_assets(self, tag: str, assets: list[Path], *, cwd: Path | None) -> None:
        """Idempotent re-run: the release exists, so re-upload assets over it.

        # ponytail: re-run only re-uploads assets. Add `gh release edit --notes-file`
        # here if editing notes on re-run is ever needed.
        """
        argv = ["gh", "release", "upload", tag, *[str(a) for a in assets], "--clobber"]
        if self.config.repo:
            argv += ["--repo", self.config.repo]
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            raise GitHubReleaseError(f"gh release upload failed: {self._last_line(result.stderr)}")
        logger.info(f"Assets uploaded to existing release {tag}.")

    @staticmethod
    def _write_temp_notes(notes: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(notes)
            return Path(f.name)

    @staticmethod
    def _last_line(stderr: str) -> str:
        lines = [line for line in stderr.strip().splitlines() if line.strip()]
        return lines[-1] if lines else "(no output)"
