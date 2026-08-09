"""Full-release orchestration for the `create` subcommand.

Sequences the project's existing batch files, git, and (only when release notes
are missing) a headless Codex call. It does not reimplement build/version logic —
each step shells out through ``bat_runner``.
"""

import logging
from pathlib import Path

from .bat_runner import bat_command, capture_command, run_command
from .create_config import CreateConfig
from .exceptions import ReleaseCreateError

logger = logging.getLogger(__name__)

RELEASE_TYPE = "RELEASE"
INTERNAL_TYPE = "INTERNAL"


class ReleaseCreator:
    """Orchestrates the full-release workflow (mirrors ReleaseManager's shape)."""

    def __init__(
        self,
        config: CreateConfig,
        project_root: Path,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.root = project_root
        self.dry_run = dry_run

    def create(self, internal: bool = False) -> bool:
        """Run the full release. Returns True on success."""
        label = self._compute_label()
        logger.info(f"Next release label: {label}")

        if not internal:
            self._ensure_notes(label)

        # Bump first, ship next: the counter is now the about-to-ship build. If a
        # later step fails, roll it back so the label doesn't drift ahead.
        self._run_bat(self.config.bats.build_increment)
        try:
            if not self.config.english_only:
                self._run_bat(self.config.bats.translate)
            self._run_bat(self.config.bats.build)
        except ReleaseCreateError:
            logger.error("Build step failed; rolling back the build counter.")
            self._run_bat(self.config.bats.build_decrement)
            raise

        if self._publish(label):
            self._commit_and_tag(label, internal)
        else:
            logger.info(
                f"Not published. Built artifact for {label}; skipping commit and tag."
            )
        return True

    def _run_bat(self, bat_path: str) -> None:
        run_command(bat_command(bat_path), self.root, self.dry_run)

    def _compute_label(self) -> str:
        """Compute the next label as version + (current build + 1)."""
        version_out = capture_command(bat_command(self.config.bats.version_get), self.root)
        build_out = capture_command(bat_command(self.config.bats.build_get), self.root)

        # version_get may print a bare version ("1.0.0") or a full label
        # ("1.0.0_21"); strip a trailing build segment either way.
        version = version_out.rsplit("_", 1)[0].strip()
        if not version:
            raise ReleaseCreateError(
                f"version_get returned no version (output: {version_out!r})"
            )
        try:
            next_build = int(build_out) + 1
        except ValueError as e:
            raise ReleaseCreateError(
                f"build_get returned a non-integer build: {build_out!r}"
            ) from e

        return self.config.label_format.format(version=version, build=next_build)

    def _ensure_notes(self, label: str) -> None:
        """Ensure en.json exists for the shipping label; author via Codex if not."""
        en_path = self.root / self.config.notes_dir / label / self.config.en_file
        if en_path.exists():
            logger.info(f"Release notes present: {en_path}")
            return

        logger.info(
            f"Release notes missing for {label}; invoking Codex to author "
            f"{self.config.en_file}."
        )
        run_command(
            ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox",
             self._notes_prompt(label)],
            self.root,
            self.dry_run,
        )
        if self.dry_run:
            return
        if not en_path.exists():
            raise ReleaseCreateError(
                f"Codex did not create {en_path}. Author it manually (or run "
                f"/release:create-release-notes) for {label}, then re-run."
            )

    def _notes_prompt(self, label: str) -> str:
        return (
            f"Author ONLY {self.config.en_file} for release {label} following the "
            f"release-create-release-notes skill. Write it to "
            f"{self.config.notes_dir}/{label}/{self.config.en_file}. Do NOT translate "
            f"and do NOT build — those are handled by the release script."
        )

    def _publish(self, label: str) -> bool:
        """The single interactive gate. Returns True if the release was published."""
        publish_bat = self.config.bats.publish
        if not publish_bat:
            logger.info("No publish bat configured; build only.")
            return False

        platform = self.config.publish_platform or "the release target"
        if self.dry_run:
            logger.info(f"[DRY RUN] Would prompt: Publish {label} to {platform}? [y/N]")
            self._run_bat(publish_bat)
            return True  # dry-run assumes 'yes' so downstream commands are shown

        response = input(f"Publish {label} to {platform}? [y/N]: ")
        if response.strip().lower() != "y":
            logger.info("Publish declined by user.")
            return False
        self._run_bat(publish_bat)
        return True

    def _commit_and_tag(self, label: str, internal: bool) -> None:
        release_type = INTERNAL_TYPE if internal else RELEASE_TYPE
        message = f"{release_type} ({self.config.scope}): {label}"
        # add -A so a freshly created release_notes/<label>/ folder is included.
        run_command(["git", "add", "-A"], self.root, self.dry_run)
        run_command(["git", "commit", "-m", message], self.root, self.dry_run)
        run_command(["git", "tag", label], self.root, self.dry_run)
