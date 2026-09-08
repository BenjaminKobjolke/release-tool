"""Tests for the recursive directory upload behind the `sync` command."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from release_tool.config import FTPConfig
from release_tool.directory_sync import DirectorySync
from release_tool.ftp_client import FTPClient, RemoteFile
from release_tool.sync_config import SyncConfig


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A project root holding a `releases` tree with one excluded subfolder."""
    releases = tmp_path / "releases"
    (releases / "windows").mkdir(parents=True)
    (releases / "linux").mkdir()
    (releases / "top.txt").write_bytes(b"top")
    (releases / "linux" / "app.tar").write_bytes(b"linux-app")
    (releases / "windows" / "app.exe").write_bytes(b"windows-app")
    return tmp_path


def make_config(remote_path: str = "/downloads/", **overrides: object) -> SyncConfig:
    """A SyncConfig with test defaults, overridable per case."""
    fields: dict[str, object] = {
        "ftp": FTPConfig(
            host="ftp.example.com",
            port=21,
            username="testuser",
            password="testpass",
            remote_path=remote_path,
        ),
        "local_dir": Path("releases"),
        "exclude": [],
        "skip_unchanged": True,
    }
    fields.update(overrides)
    return SyncConfig(**fields)  # type: ignore[arg-type]


def make_client(sizes: dict[str, int] | None = None) -> MagicMock:
    """An FTPClient double whose stat_file answers from a name->size map."""
    client = MagicMock(spec=FTPClient)
    known = sizes or {}
    client.stat_file.side_effect = lambda name: (
        RemoteFile(exists=True, size=known[name]) if name in known else RemoteFile(False, None)
    )
    return client


class TestDirectorySync:
    """Tests for DirectorySync.sync."""

    def test_uploads_every_file_under_its_remote_directory(self, tree: Path) -> None:
        """Each file lands in remote_path + its path relative to local_dir."""
        client = make_client()
        assert DirectorySync(make_config(), tree, client).sync() is True

        uploaded = {call.args[1] for call in client.upload_file.call_args_list}
        assert uploaded == {"top.txt", "app.tar", "app.exe"}
        ensured = {call.args[0] for call in client.ensure_directory.call_args_list}
        assert ensured == {"/downloads", "/downloads/linux", "/downloads/windows"}

    def test_exclude_glob_skips_a_subtree(self, tree: Path) -> None:
        """`windows/**` drops the whole folder, matching the rclone call it replaces."""
        client = make_client()
        DirectorySync(make_config(exclude=["windows/**"]), tree, client).sync()

        uploaded = {call.args[1] for call in client.upload_file.call_args_list}
        assert uploaded == {"top.txt", "app.tar"}

    def test_exclude_matches_a_bare_directory_name(self, tree: Path) -> None:
        """A pattern naming the folder itself excludes its contents too."""
        client = make_client()
        DirectorySync(make_config(exclude=["windows"]), tree, client).sync()

        uploaded = {call.args[1] for call in client.upload_file.call_args_list}
        assert uploaded == {"top.txt", "app.tar"}

    def test_skip_unchanged_skips_only_matching_sizes(self, tree: Path) -> None:
        """Same remote size means skip; a different size re-uploads."""
        client = make_client({"top.txt": len(b"top"), "app.tar": 1})
        DirectorySync(make_config(), tree, client).sync()

        uploaded = {call.args[1] for call in client.upload_file.call_args_list}
        assert uploaded == {"app.tar", "app.exe"}

    def test_skip_unchanged_off_uploads_everything(self, tree: Path) -> None:
        """With the check off the remote is never stat'd."""
        client = make_client({"top.txt": len(b"top")})
        DirectorySync(make_config(skip_unchanged=False), tree, client).sync()

        assert client.stat_file.call_count == 0
        assert client.upload_file.call_count == 3

    def test_root_remote_path_builds_absolute_paths(self, tree: Path) -> None:
        """remote_path = / must not produce a doubled slash."""
        client = make_client()
        DirectorySync(make_config(remote_path="/"), tree, client).sync()

        ensured = {call.args[0] for call in client.ensure_directory.call_args_list}
        assert ensured == {"/", "/linux", "/windows"}

    def test_missing_local_dir_fails(self, tmp_path: Path) -> None:
        """A local_dir that is not there is an error, not a silent no-op."""
        client = make_client()
        assert DirectorySync(make_config(), tmp_path, client).sync() is False
        assert client.upload_file.call_count == 0

    def test_dry_run_touches_nothing_remote(
        self, tree: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A dry run never connects and lists what it would upload."""
        client = make_client()
        with caplog.at_level("INFO"):
            assert DirectorySync(make_config(), tree, client, dry_run=True).sync() is True

        assert client.connection.call_count == 0
        assert client.upload_file.call_count == 0
        assert "/downloads/linux/app.tar" in caplog.text
