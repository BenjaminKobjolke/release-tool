"""Full-release orchestration for the `create` subcommand.

Sequences the project's existing batch files, git, and (only when release notes
are missing) a headless Codex call. It does not reimplement build/version logic —
each step shells out through ``bat_runner``.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from .bat_runner import bat_command, capture_command, run_command
from .create_config import CreateConfig
from .exceptions import ReleaseCreateError

logger = logging.getLogger(__name__)

RELEASE_TYPE = "RELEASE"
INTERNAL_TYPE = "INTERNAL"


@dataclass(frozen=True)
class ReleaseLabels:
    """The two labels a release deals with, derived from one version read.

    ``previous`` is the version currently online (the file being replaced) — used
    to name its backup folder. ``shipping`` is the label being released now. Both
    come from the same source, so they can never drift apart.
    """

    previous: str
    shipping: str


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
        labels = self._compute_labels()
        logger.info(f"Next release label: {labels.shipping}")

        if not internal:
            self._ensure_notes(labels.shipping)

        # Bump first, ship next: the counter/version is now the about-to-ship
        # label. If a later step fails, roll it back so it doesn't drift ahead.
        self._run_bat(self.config.bats.build_increment)
        try:
            if not self.config.english_only:
                self._run_bat(self.config.bats.translate)
            self._run_bat(self.config.bats.build)
        except ReleaseCreateError:
            logger.error("Build step failed; rolling back the version/build counter.")
            self._run_bat(self.config.bats.build_decrement)
            raise

        # Record the previous (online) version so the publish bat can name its
        # backup folder — whether publish runs now or is run by hand later.
        self._write_previous_version(labels.previous)
        # Two independent gates: shipping and recording the release are separate
        # decisions, so declining one does not skip the other.
        self._maybe_publish(labels)
        self._maybe_commit(labels.shipping, internal)
        return True

    def _run_bat(self, bat_path: str) -> None:
        run_command(bat_command(bat_path), self.root, self.dry_run)

    def _compute_labels(self) -> ReleaseLabels:
        """Derive the previous (online) and shipping labels from version/build."""
        version_out = capture_command(bat_command(self.config.bats.version_get), self.root)

        # version_get may print a bare version ("1.0.0") or a full label
        # ("1.0.0_21"); strip a trailing build segment either way.
        version = version_out.rsplit("_", 1)[0].strip()
        if not version:
            raise ReleaseCreateError(f"version_get returned no version (output: {version_out!r})")

        if self.config.versioning == "semver":
            return self._semver_labels(version)
        return self._build_labels(version)

    def _semver_labels(self, version: str) -> ReleaseLabels:
        """Semver mode: shipping = version with its last segment +1."""
        parts = version.split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except ValueError as e:
            raise ReleaseCreateError(
                f"version_get returned a non-numeric last segment: {version!r}"
            ) from e
        return ReleaseLabels(previous=version, shipping=".".join(parts))

    def _build_labels(self, version: str) -> ReleaseLabels:
        """Build mode: shipping = version + (current build + 1)."""
        build_out = capture_command(bat_command(self.config.bats.build_get), self.root)
        try:
            build = int(build_out)
        except ValueError as e:
            raise ReleaseCreateError(
                f"build_get returned a non-integer build: {build_out!r}"
            ) from e
        return ReleaseLabels(
            previous=self.config.label_format.format(version=version, build=build),
            shipping=self.config.label_format.format(version=version, build=build + 1),
        )

    def _ensure_notes(self, label: str) -> None:
        """Ensure en.json exists for the shipping label; author via Codex if not."""
        en_path = self.root / self.config.notes_dir / label / self.config.en_file
        if en_path.exists():
            logger.info(f"Release notes present: {en_path}")
            return

        logger.info(
            f"Release notes missing for {label}; invoking Codex to author {self.config.en_file}."
        )
        run_command(
            [
                "codex",
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                self._notes_prompt(label),
            ],
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

    def _write_previous_version(self, previous: str) -> None:
        """Record the previous (online) version for the publish bat to read."""
        target = self.root / self.config.previous_version_file
        if self.dry_run:
            logger.info(f"[DRY RUN] Would write {previous!r} to {target}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{previous}\n", encoding="utf-8")
        logger.info(f"Wrote previous version {previous!r} to {target}")

    def _maybe_publish(self, labels: ReleaseLabels) -> None:
        """Ask whether to publish; run the publish bat (which reads the version file)."""
        publish_bat = self.config.bats.publish
        if not publish_bat:
            logger.info("No publish bat configured; skipping publish.")
            return

        platform = self.config.publish_platform or "the release target"
        prompt = f"Publish {labels.shipping} to {platform}? [y/N]"
        if self.dry_run:
            logger.info(f"[DRY RUN] Would prompt: {prompt}")
            self._run_bat(publish_bat)
            return

        if input(f"{prompt}: ").strip().lower() != "y":
            logger.info("Publish declined by user.")
            return
        self._run_bat(publish_bat)

    def _maybe_commit(self, label: str, internal: bool) -> None:
        """Ask whether to commit, tag and push the release."""
        prompt = f"Commit, tag and push {label}? [y/N]"
        if self.dry_run:
            logger.info(f"[DRY RUN] Would prompt: {prompt}")
        elif input(f"{prompt}: ").strip().lower() != "y":
            logger.info("Commit/tag/push declined by user.")
            return

        release_type = INTERNAL_TYPE if internal else RELEASE_TYPE
        message = f"{release_type} ({self.config.scope}): {label}"
        # add -A so a freshly created release_notes/<label>/ folder is included.
        run_command(["git", "add", "-A"], self.root, self.dry_run)
        run_command(["git", "commit", "-m", message], self.root, self.dry_run)
        run_command(["git", "tag", label], self.root, self.dry_run)
        run_command(["git", "push"], self.root, self.dry_run)
        run_command(["git", "push", "origin", label], self.root, self.dry_run)
