"""Recursive local-directory upload behind the `sync` command.

Replaces the `rclone copy <dir> ftp-remote:` calls the bat chains used. Uploads
are serial on the one FTPClient connection — rclone's `--transfers 4` was a
throughput knob, not a correctness one, and the calls being replaced already
pinned it to 1.

Deliberately not shared with ReleaseNotesUploader: that one diffs whole version
folders by name and uploads a folder only if it is absent remotely, while this
one diffs per file by size. Folding them together would change notes behavior.
"""

import logging
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from .ftp_client import FTPClient
from .sync_config import SyncConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncItem:
    """One local file paired with the remote directory and name it lands in."""

    local: Path
    remote_dir: str
    name: str

    @property
    def remote_path(self) -> str:
        """Full remote path, for logging — derived so the two cannot drift."""
        return f"{self.remote_dir.rstrip('/')}/{self.name}"


class DirectorySync:
    """Uploads a local directory tree to a remote FTP path."""

    def __init__(
        self,
        config: SyncConfig,
        project_root: Path,
        client: FTPClient,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.client = client
        self.dry_run = dry_run

    def sync(self) -> bool:
        """Upload every non-excluded file under local_dir. True on success."""
        local_dir = (self.project_root / self.config.local_dir).resolve()

        if not local_dir.is_dir():
            logger.error(f"Sync local_dir not found or not a directory: {local_dir}")
            return False

        items = self._collect(local_dir)
        if not items:
            logger.info(f"No files to sync under {local_dir}")
            return True

        if self.dry_run:
            return self._preview(local_dir, items)

        return self._upload(items)

    def _collect(self, local_dir: Path) -> list[SyncItem]:
        """Walk local_dir into the remote placement each file gets."""
        base = _remote_base(self.config.ftp.remote_path)

        items = []
        for path in sorted(local_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = PurePosixPath(path.relative_to(local_dir).as_posix())
            if self._excluded(relative):
                logger.debug(f"Excluded: {relative}")
                continue
            items.append(
                SyncItem(
                    local=path,
                    remote_dir=_remote_join(base, relative.parent),
                    name=relative.name,
                )
            )
        return items

    def _excluded(self, relative: PurePosixPath) -> bool:
        """Match the path and each parent, so `windows` and `windows/**` both work."""
        candidates = [str(relative)] + [str(p) for p in relative.parents if str(p) != "."]
        return any(
            fnmatch(candidate, pattern)
            for candidate in candidates
            for pattern in self.config.exclude
        )

    def _preview(self, local_dir: Path, items: list[SyncItem]) -> bool:
        """List what would be uploaded without connecting to the server."""
        logger.info("[DRY RUN] Directory sync:")
        logger.info(f"[DRY RUN] Local dir: {local_dir}")
        logger.info(f"[DRY RUN] Host: {self.config.ftp.host}:{self.config.ftp.port}")
        logger.info(f"[DRY RUN] Remote path: {self.config.ftp.remote_path}")
        if self.config.exclude:
            logger.info(f"[DRY RUN] Exclude: {', '.join(self.config.exclude)}")
        logger.info(f"[DRY RUN] Skip files whose remote size matches: {self.config.skip_unchanged}")
        for item in items:
            logger.info(f"[DRY RUN] Would upload {item.local} -> {item.remote_path}")
        logger.info(f"[DRY RUN] {len(items)} file(s) selected")
        return True

    def _upload(self, items: list[SyncItem]) -> bool:
        """Upload the collected files, one remote directory at a time."""
        uploaded = 0
        skipped = 0

        with self.client.connection():
            for remote_dir, group in _group_by_directory(items):
                self.client.ensure_directory(remote_dir)
                self.client.change_directory(remote_dir)
                for item in group:
                    if self._unchanged(item):
                        logger.debug(f"Unchanged, skipping: {item.remote_path}")
                        skipped += 1
                        continue
                    self.client.upload_file(item.local, item.name)
                    uploaded += 1

        logger.info(f"Sync complete: {uploaded} uploaded, {skipped} unchanged")
        return True

    def _unchanged(self, item: SyncItem) -> bool:
        """Size-only comparison: plain FTP has no mtime we can trust across servers.

        An unknown remote size counts as changed, so a server that refuses SIZE
        re-uploads rather than silently skipping.
        """
        if not self.config.skip_unchanged:
            return False
        return self.client.stat_file(item.name).size == item.local.stat().st_size


def _remote_base(remote_path: str) -> str:
    """The absolute remote root every uploaded path is built from."""
    return "/" + remote_path.strip("/")


def _remote_join(base: str, relative_dir: PurePosixPath) -> str:
    """Append a relative directory to the remote base, without a doubled slash."""
    if str(relative_dir) == ".":
        return base
    return f"{base.rstrip('/')}/{relative_dir}"


def _group_by_directory(items: list[SyncItem]) -> list[tuple[str, list[SyncItem]]]:
    """Bucket items by remote directory so each one is created and entered once.

    A plain sort does not make same-directory files contiguous (`a/b.txt` sorts
    before `a/c/d.txt` which sorts before `a/e.txt`), so group explicitly.
    """
    groups: dict[str, list[SyncItem]] = {}
    for item in items:
        groups.setdefault(item.remote_dir, []).append(item)
    return list(groups.items())
