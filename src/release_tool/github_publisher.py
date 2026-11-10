"""GitHub Releases publishing.

Shells out to the ``gh`` CLI (the same convention as the PowerShell/git/codex
calls elsewhere in this project) so the package stays dependency-free — no
``requests``/``PyGithub``, ``gh`` owns auth via ``gh auth login``.
"""

import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import GitHubReleaseError
from .github_release_notes import render_notes_markdown

logger = logging.getLogger(__name__)

_ALREADY_EXISTS_MARKER = "already exists"
_NOT_FOUND_MARKER = "release not found"
_NETWORK_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "connection attempt failed",
    "wsarecv",
    "wsasend",
    "dial tcp",
    "read tcp",
    "write tcp",
    "unexpected eof",
    "tls handshake",
)
_HTTP_5XX = re.compile(r"http 5\d\d", re.IGNORECASE)


def _is_network_error(stderr: str) -> bool:
    """Return whether a gh error looks transient and safe to reconcile remotely."""
    lowered = stderr.lower()
    return _HTTP_5XX.search(stderr) is not None or any(
        marker in lowered for marker in _NETWORK_ERROR_MARKERS
    )


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
        notes_json: Path | None = None,
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
            if asset.exists():
                continue
            # A dry run never builds, so a not-yet-built asset is expected there.
            if dry_run:
                logger.warning(f"[DRY RUN] Asset not built yet: {asset}")
                continue
            raise GitHubReleaseError(f"Asset not found: {asset}")

        cleanup_notes_file: Path | None = None
        original_notes = notes
        original_notes_file = notes_file
        try:
            if notes_json is not None and notes is None and notes_file is None:
                notes = render_notes_markdown(notes_json)
            if notes is not None and notes_file is None:
                notes_file = cleanup_notes_file = self._write_temp_notes(notes)

            argv = self._build_create_argv(tag, assets, title=title, notes_file=notes_file)

            if dry_run:
                logger.info(f"[DRY RUN] Would run: {' '.join(str(a) for a in argv)}")
                return

            try:
                self._create_or_recover(tag, assets, argv, cwd=cwd)
            except GitHubReleaseError as error:
                hint = self._recovery_command(
                    tag,
                    assets,
                    title,
                    notes_json,
                    original_notes,
                    original_notes_file,
                    cwd,
                )
                raise GitHubReleaseError(
                    f"{error}\nPublish the existing build without rebuilding: {hint}"
                ) from error
        finally:
            if cleanup_notes_file is not None:
                cleanup_notes_file.unlink(missing_ok=True)

    def _create_or_recover(
        self,
        tag: str,
        assets: list[Path],
        create_argv: list[str],
        *,
        cwd: Path | None,
    ) -> None:
        """Create once, reconciling remote state before the one network retry."""
        for attempt in range(2):
            logger.info(f"Creating GitHub Release {tag}")
            result = subprocess.run(create_argv, cwd=cwd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"GitHub Release {tag} created.")
                return

            if _ALREADY_EXISTS_MARKER in result.stderr.lower():
                logger.info(f"Release {tag} already exists; uploading assets instead.")
                self._upload_assets(tag, assets, cwd=cwd)
                return

            if attempt == 1 or not _is_network_error(result.stderr):
                raise GitHubReleaseError(
                    f"gh release create failed: {self._last_line(result.stderr)}"
                )

            logger.warning(
                f"GitHub Release {tag} creation failed: {self._last_line(result.stderr)}; "
                "checking remote state."
            )
            try:
                is_draft = self._release_is_draft(tag, cwd=cwd)
            except GitHubReleaseError as error:
                raise GitHubReleaseError(
                    f"gh release create failed: {self._last_line(result.stderr)}"
                ) from error

            if is_draft is None:
                continue

            self._upload_assets(tag, assets, cwd=cwd)
            if is_draft:
                self._publish_draft(tag, cwd=cwd)
            logger.info(f"Recovered GitHub Release {tag} after a network error.")
            return

        raise AssertionError("The GitHub release retry loop exited unexpectedly")

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
        return argv + self._repo_args()

    def _release_is_draft(self, tag: str, *, cwd: Path | None) -> bool | None:
        """Return the remote release's draft state, or None when the tag is absent."""
        argv = ["gh", "release", "view", tag, "--json", "isDraft", "--jq", ".isDraft"]
        result = subprocess.run(
            argv + self._repo_args(), cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            if _NOT_FOUND_MARKER in result.stderr.lower():
                return None
            raise GitHubReleaseError(
                f"gh release view failed: {self._last_line(result.stderr)}"
            )

        value = result.stdout.strip().lower()
        if value == "true":
            return True
        if value == "false":
            return False
        raise GitHubReleaseError(f"gh release view returned an invalid draft state: {value!r}")

    def _publish_draft(self, tag: str, *, cwd: Path | None) -> None:
        """Publish an existing draft release."""
        argv = ["gh", "release", "edit", tag, "--draft=false"]
        result = subprocess.run(
            argv + self._repo_args(), cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise GitHubReleaseError(
                f"gh release edit failed: {self._last_line(result.stderr)}"
            )

    def _repo_args(self) -> list[str]:
        if self.config.repo:
            return ["--repo", self.config.repo]
        return []

    def _recovery_command(
        self,
        tag: str,
        assets: list[Path],
        title: str | None,
        notes_json: Path | None,
        notes: str | None,
        notes_file: Path | None,
        cwd: Path | None,
    ) -> str:
        """Build a repeatable command to publish this already-built release."""
        argv = [
            "release-tool",
            "github-release",
            tag,
            *[str(asset) for asset in assets],
            "--title",
            title or tag,
        ]
        if notes_file is not None:
            argv += ["--notes-file", str(notes_file)]
        elif notes_json is not None and notes is None:
            argv += ["--notes-json", str(notes_json)]
        elif notes is not None:
            argv += ["--notes", notes]
        argv += self._repo_args()

        command = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
        if cwd is not None:
            command += f" (run from {cwd})"
        return command

    def _upload_assets(self, tag: str, assets: list[Path], *, cwd: Path | None) -> None:
        """Idempotent re-run: the release exists, so re-upload assets over it.

        # ponytail: re-run only re-uploads assets. Add `gh release edit --notes-file`
        # here if editing notes on re-run is ever needed.
        """
        argv = ["gh", "release", "upload", tag, *[str(a) for a in assets], "--clobber"]
        argv += self._repo_args()
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
