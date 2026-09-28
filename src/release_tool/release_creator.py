"""Full-release orchestration for the `create` subcommand.

Sequences the project's existing batch files, git, and (only when release notes
are missing) a headless Codex call. It does not reimplement build/version logic —
each step shells out through ``bat_runner``.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from .bat_runner import bat_command, capture_command, run_command
from .cli_support import confirm
from .create_config import CreateConfig, PublishChannel
from .exceptions import ReleaseCreateError
from .github_publisher import GitHubPublisher, render_notes_markdown

logger = logging.getLogger(__name__)

RELEASE_TYPE = "RELEASE"
INTERNAL_TYPE = "INTERNAL"


@dataclass(frozen=True)
class ReleaseLabels:
    """The two labels a release deals with, derived from one version read.

    ``previous`` is the version currently online (the file being replaced) — used
    to name its backup folder. ``shipping`` is the label being released now.
    ``notes`` keys the release-notes subfolder — usually equal to ``shipping``, but
    ``notes_label_format`` can decouple it (e.g. build-number folders under a
    version+build tag). All three derive from the same version/build read, so they
    can never drift apart.
    """

    previous: str
    shipping: str
    notes: str


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
            self._ensure_notes(labels.notes)

        # Bump first, ship next: the counter/version is now the about-to-ship
        # label. If a later step fails, roll it back so it doesn't drift ahead.
        # A self-contained build bat (a monolithic release script) already does
        # its own bump/translate/rollback, so create must not repeat any of it.
        self_contained = self.config.build_self_contained
        if not self_contained:
            self._run_bat(self.config.bats.build_increment)
        try:
            if not self.config.english_only and not self_contained:
                self._run_bat(self.config.bats.translate)
            self._run_bat(self.config.bats.build)
        except ReleaseCreateError:
            if not self_contained:
                logger.error("Build step failed; rolling back the version/build counter.")
                self._run_bat(self.config.bats.build_decrement)
            raise

        # Record the previous (online) version so the publish bat can name its
        # backup folder — whether publish runs now or is run by hand later.
        self._write_previous_version(labels.previous)
        # Two independent gates: shipping and recording the release are separate
        # decisions, so declining one does not skip the other.
        self._maybe_publish(labels)
        if self._maybe_commit(labels.shipping, internal):
            self._maybe_github_release(labels, internal)
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
        shipping = ".".join(parts)
        # semver has no build counter, so notes share the shipping version.
        return ReleaseLabels(previous=version, shipping=shipping, notes=shipping)

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
            notes=self.config.notes_label_format.format(version=version, build=build + 1),
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
            close_stdin=True,
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

    def _publish_channels(self) -> list[PublishChannel]:
        """The configured publish gates: multi-channel config, or the legacy
        single-bat fields for callers that construct CreateConfig directly."""
        if self.config.publish_channels:
            return self.config.publish_channels
        if self.config.bats.publish:
            name = self.config.publish_platform or "the release target"
            return [PublishChannel(name=name, bat=self.config.bats.publish)]
        return []

    def _maybe_publish(self, labels: ReleaseLabels) -> None:
        """Ask whether to publish each configured channel independently."""
        channels = self._publish_channels()
        if not channels:
            logger.info("No publish bat configured; skipping publish.")
            return

        for channel in channels:
            prompt = f"Publish {labels.shipping} to {channel.name}? [y/N]"
            if self.dry_run:
                logger.info(f"[DRY RUN] Would prompt: {prompt}")
                self._run_bat(channel.bat)
                continue

            if not confirm(prompt):
                logger.info(f"Publish to {channel.name} declined by user.")
                continue
            self._run_bat(channel.bat)

    def _maybe_commit(self, label: str, internal: bool) -> bool:
        """Ask whether to commit, tag and push the release. Returns True if it ran —
        the GitHub Release gate depends on the tag having actually been pushed."""
        prompt = f"Commit, tag and push {label}? [y/N]"
        if self.dry_run:
            logger.info(f"[DRY RUN] Would prompt: {prompt}")
        elif not confirm(prompt):
            logger.info("Commit/tag/push declined by user.")
            return False

        release_type = INTERNAL_TYPE if internal else RELEASE_TYPE
        message = f"{release_type} ({self.config.scope}): {label}"
        # add -A so a freshly created release_notes/<label>/ folder is included.
        run_command(["git", "add", "-A"], self.root, self.dry_run)
        run_command(["git", "commit", "-m", message], self.root, self.dry_run)
        run_command(["git", "tag", label], self.root, self.dry_run)
        run_command(["git", "push"], self.root, self.dry_run)
        run_command(["git", "push", "origin", label], self.root, self.dry_run)
        return True

    def _maybe_github_release(self, labels: ReleaseLabels, internal: bool) -> None:
        """Ask whether to create/update the GitHub Release for the just-pushed tag."""
        cfg = self.config.github_release
        if cfg is None:
            logger.info("No GitHub Release configured; skipping.")
            return

        tag = self._format_label(cfg.tag_format, labels)
        title = self._format_label(cfg.title_format, labels)
        prompt = f"Create GitHub Release {tag}? [y/N]"
        if self.dry_run:
            logger.info(f"[DRY RUN] Would prompt: {prompt}")
        elif not confirm(prompt):
            logger.info("GitHub Release declined by user.")
            return

        assets = [self.root / asset for asset in cfg.assets]
        notes = None
        if not internal:
            notes_path = self.root / self.config.notes_dir / labels.notes / self.config.en_file
            if notes_path.exists():
                notes = render_notes_markdown(notes_path)

        GitHubPublisher(cfg).publish(
            tag, assets, title=title, notes=notes, cwd=self.root, dry_run=self.dry_run
        )

    @staticmethod
    def _format_label(fmt: str, labels: ReleaseLabels) -> str:
        """Resolve a tag/title format string against the shipping label.

        version/build/label all resolve to the same shipping string — ReleaseLabels
        does not retain the version and build parts separately once combined.
        """
        return fmt.format(version=labels.shipping, build=labels.shipping, label=labels.shipping)
