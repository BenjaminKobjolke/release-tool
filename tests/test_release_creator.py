"""Tests for the full-release orchestration (ReleaseCreator)."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_tool.create_config import BatsConfig, CreateConfig, PublishChannel
from release_tool.exceptions import ConfigurationError, ReleaseCreateError
from release_tool.github_publisher import GitHubReleaseConfig
from release_tool.release_creator import ReleaseCreator
from release_tool.release_labels import VersionNameBump
from release_tool.version_file import VersionFile


def make_config(
    *,
    publish: str | None = "tools/publish.bat",
    english_only: bool = False,
    versioning: str = "build",
    label_format: str = "{version}_{build}",
    notes_label_format: str = "{version}_{build}",
    build_self_contained: bool = False,
    publish_channels: list[PublishChannel] | None = None,
    github_release: GitHubReleaseConfig | None = None,
) -> CreateConfig:
    bats = BatsConfig(
        version_get="tools/version_get.bat",
        build_get="tools/build_get.bat",
        build_increment="tools/build_increment.bat",
        build_decrement="tools/build_decrement.bat",
        translate="tools/translate.bat",
        build="tools/build.bat",
        publish=publish,
    )
    return CreateConfig(
        scope="app",
        publish_platform="Store",
        notes_dir="release_notes",
        en_file="en.json",
        label_format=label_format,
        notes_label_format=notes_label_format,
        versioning=versioning,
        previous_version_file="tools/previous_version.txt",
        english_only=english_only,
        build_self_contained=build_self_contained,
        publish_channels=publish_channels or [],
        bats=bats,
        github_release=github_release,
    )


def ran(mock_run: MagicMock) -> list[list[str]]:
    """Return the command lists passed to the mocked run_command."""
    return [call.args[0] for call in mock_run.call_args_list]


def uses(cmds: list[list[str]], needle: str) -> bool:
    return any(needle in part for cmd in cmds for part in cmd)


def fail_on_build(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
    """run_command side_effect: raise once the build bat itself is invoked."""
    if any(part.endswith("build.bat") for part in cmd):
        raise ReleaseCreateError("build blew up")


def two_publish_channels() -> list[PublishChannel]:
    """A Website + Google Play channel pair, shared by the multi-channel tests."""
    return [
        PublishChannel(name="Website", bat="tools/publish_website.bat"),
        PublishChannel(name="Google Play", bat="tools/publish_play.bat"),
    ]


def label_capture(mock_capture: MagicMock, version: str = "1.0.0", build: str = "21") -> None:
    """Stub version_get/build_get so the computed label is <version>_<build+1>."""
    mock_capture.side_effect = [version, build]


def prepare_notes(root: Path, label: str = "1.0.0_22") -> None:
    """Create release_notes/<label>/en.json so the notes step is satisfied."""
    notes = root / "release_notes" / label
    notes.mkdir(parents=True)
    (notes / "en.json").write_text("{}")


class TestComputeLabel:
    @patch("release_tool.release_creator.capture_command")
    def test_bare_version(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        labels = creator._compute_labels()
        assert labels.shipping == "1.0.0_22"
        assert labels.previous == "1.0.0_21"

    @patch("release_tool.release_creator.capture_command")
    def test_full_label_version(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        """version_get printing a full label is trimmed to the bare version."""
        mock_capture.side_effect = ["1.0.0_21", "21"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        assert creator._compute_labels().shipping == "1.0.0_22"

    @patch("release_tool.release_creator.capture_command")
    def test_non_integer_build_raises(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["1.0.0", "not-a-number"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="non-integer build"):
            creator._compute_labels()

    @patch("release_tool.release_creator.capture_command")
    def test_empty_version_raises(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["", "21"]
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="no version"):
            creator._compute_labels()

    @patch("release_tool.release_creator.capture_command")
    def test_notes_label_defaults_to_shipping(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        """Matching note and tag formats produce the same shipping label."""
        label_capture(mock_capture)
        labels = ReleaseCreator(make_config(), tmp_path, dry_run=True)._compute_labels()
        assert labels.notes == labels.shipping == "1.0.0_22"

    @patch("release_tool.release_creator.capture_command")
    def test_notes_label_decoupled_from_commit_label(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        """notes_label_format keys the notes folder independently of the commit/tag label."""
        mock_capture.side_effect = ["1.0.0", "21"]
        config = make_config(label_format="{version}+{build}", notes_label_format="{build}")
        labels = ReleaseCreator(config, tmp_path, dry_run=True)._compute_labels()
        assert labels.shipping == "1.0.0+22"  # commit/tag label
        assert labels.notes == "22"  # notes-folder key


class TestSemverLabels:
    @patch("release_tool.release_creator.capture_command")
    def test_semver_bumps_last_segment(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        mock_capture.side_effect = ["0.1.6"]  # build_get is never read in semver
        creator = ReleaseCreator(make_config(versioning="semver"), tmp_path, dry_run=True)
        labels = creator._compute_labels()
        assert labels.previous == "0.1.6"
        assert labels.shipping == "0.1.7"

    @patch("release_tool.release_creator.capture_command")
    def test_semver_non_numeric_last_segment_raises(
        self, mock_capture: MagicMock, tmp_path: Path
    ) -> None:
        mock_capture.side_effect = ["0.1.x"]
        creator = ReleaseCreator(make_config(versioning="semver"), tmp_path, dry_run=True)
        with pytest.raises(ReleaseCreateError, match="non-numeric last segment"):
            creator._compute_labels()

    @patch("builtins.input", side_effect=["y", "n"])  # publish yes, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_semver_writes_previous_version_file(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_capture.side_effect = ["0.1.6"]
        prepare_notes(tmp_path, label="0.1.7")

        creator = ReleaseCreator(make_config(versioning="semver"), tmp_path, dry_run=False)
        creator.create(internal=False)

        prev_file = tmp_path / "tools" / "previous_version.txt"
        assert prev_file.read_text(encoding="utf-8").strip() == "0.1.6"
        # publish bat takes no args now — it reads the file itself.
        publish = next(c for c in ran(mock_run) if uses([c], "publish.bat"))
        assert publish == ["cmd", "/c", "call", "tools\\publish.bat"]


class TestCreateFlow:
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_dry_run_full_sequence(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        assert creator.create(internal=False) is True

        cmds = ran(mock_run)
        assert uses(cmds, "build_increment.bat")
        assert uses(cmds, "translate.bat")
        assert uses(cmds, "build.bat")
        assert uses(cmds, "publish.bat")
        assert uses(cmds, "git")  # commit + tag + push in dry-run assume yes
        assert ["git", "push"] in cmds  # push happens on commit
        assert ["git", "push", "origin", "1.0.0_22"] in cmds

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_missing_notes_invokes_codex(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        creator.create(internal=False)
        codex_call = next(call for call in mock_run.call_args_list if "codex" in call.args[0])
        assert codex_call.kwargs == {"close_stdin": True}
        assert all(
            call.kwargs.get("close_stdin") is not True
            for call in mock_run.call_args_list
            if call is not codex_call
        )

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_notes_lookup_uses_notes_label(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Notes in their own folder satisfy the step; commit uses the full label."""
        mock_capture.side_effect = ["1.0.0", "21"]
        prepare_notes(tmp_path, label="22")  # build-number folder, not the commit label
        config = make_config(label_format="{version}+{build}", notes_label_format="{build}")

        creator = ReleaseCreator(config, tmp_path, dry_run=True)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "codex")  # found at notes label, no authoring
        assert ["git", "push", "origin", "1.0.0+22"] in cmds  # tag uses full label

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_internal_skips_notes_and_tags_internal(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=True)
        creator.create(internal=True)

        cmds = ran(mock_run)
        assert not uses(cmds, "codex")  # notes skipped
        commit = next(c for c in cmds if c[:2] == ["git", "commit"])
        assert "INTERNAL (app): 1.0.0_22" in commit

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_english_only_skips_translate(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(english_only=True), tmp_path, dry_run=True)
        creator.create(internal=False)
        assert not uses(ran(mock_run), "translate.bat")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_build_failure_rolls_back(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        mock_run.side_effect = fail_on_build
        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)

        with pytest.raises(ReleaseCreateError, match="build blew up"):
            creator.create(internal=False)

        assert uses(ran(mock_run), "build_decrement.bat")

    @patch("builtins.input", side_effect=["n", "y"])  # publish no, commit yes
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_publish_declined_still_commits(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Publish and commit are independent — declining publish still commits."""
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "publish.bat")
        assert any(c[:2] == ["git", "commit"] for c in cmds)
        assert ["git", "push"] in cmds

    @patch("builtins.input", side_effect=["y", "n"])  # publish yes, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_commit_declined_still_publishes(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(), tmp_path, dry_run=False)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "publish.bat")
        assert not uses(cmds, "git")

    @patch("builtins.input", return_value="n")  # publish n/a, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_no_publish_bat_skips_publish_only(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No publish bat skips only the publish step; commit is still offered."""
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(publish=None), tmp_path, dry_run=False)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "build.bat")
        assert not uses(cmds, "publish")
        assert not uses(cmds, "git")  # commit declined above


class TestBuildSelfContained:
    """A monolithic build bat owns increment/translate/rollback itself."""

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_skips_increment_and_translate(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(build_self_contained=True), tmp_path, dry_run=True)
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert not uses(cmds, "build_increment.bat")
        assert not uses(cmds, "translate.bat")
        assert uses(cmds, "build.bat")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_build_failure_does_not_decrement(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        mock_run.side_effect = fail_on_build
        creator = ReleaseCreator(make_config(build_self_contained=True), tmp_path, dry_run=False)

        with pytest.raises(ReleaseCreateError, match="build blew up"):
            creator.create(internal=False)

        assert not uses(ran(mock_run), "build_decrement.bat")


class TestMultiChannelPublish:
    """Each publish channel is gated independently."""

    @patch("builtins.input", side_effect=["y", "n", "n"])  # website yes, play no, commit no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_each_channel_gated_independently(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        channels = two_publish_channels()

        creator = ReleaseCreator(
            make_config(publish=None, publish_channels=channels), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "publish_website.bat")
        assert not uses(cmds, "publish_play.bat")

    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_dry_run_runs_every_channel(
        self, mock_capture: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        channels = two_publish_channels()

        creator = ReleaseCreator(
            make_config(publish=None, publish_channels=channels), tmp_path, dry_run=True
        )
        creator.create(internal=False)

        cmds = ran(mock_run)
        assert uses(cmds, "publish_website.bat")
        assert uses(cmds, "publish_play.bat")


class TestGitHubReleaseGate:
    """The GitHub Release gate runs after commit/tag/push, and only if that ran."""

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", return_value="n")  # commit declined
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_no_config_skips_gate(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)

        creator = ReleaseCreator(make_config(publish=None), tmp_path, dry_run=False)
        creator.create(internal=False)

        mock_publisher_class.assert_not_called()

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", return_value="n")  # commit declined -> gate never offered
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_commit_declined_skips_gate(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        gh_config = GitHubReleaseConfig(enabled=True, assets=["target/app.exe"])

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        mock_publisher_class.assert_not_called()

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", side_effect=["y", "n"])  # commit yes, github release no
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_github_release_declined(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        gh_config = GitHubReleaseConfig(enabled=True, assets=["target/app.exe"])

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        mock_publisher_class.return_value.publish.assert_not_called()

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", side_effect=["y", "y"])  # commit yes, github release yes
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_github_release_published_after_commit(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        prepare_notes(tmp_path)
        (tmp_path / "release_notes" / "1.0.0_22" / "en.json").write_text(
            '{"title": "1.0.0_22", "notes": ["First"]}'
        )
        gh_config = GitHubReleaseConfig(
            enabled=True, repo="owner/name", assets=["target/app.exe"], tag_format="v{label}"
        )

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=False)

        mock_publisher_class.assert_called_once_with(gh_config)
        publish_call = mock_publisher_class.return_value.publish.call_args
        assert publish_call.args[0] == "v1.0.0_22"
        assert publish_call.args[1] == [tmp_path / "target" / "app.exe"]
        assert publish_call.kwargs["cwd"] == tmp_path

    @patch("release_tool.release_creator.GitHubPublisher")
    @patch("builtins.input", side_effect=["y", "y"])  # commit yes, github release yes
    @patch("release_tool.release_creator.run_command")
    @patch("release_tool.release_creator.capture_command")
    def test_internal_release_skips_notes(
        self,
        mock_capture: MagicMock,
        mock_run: MagicMock,
        mock_input: MagicMock,
        mock_publisher_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        label_capture(mock_capture)
        gh_config = GitHubReleaseConfig(enabled=True, assets=["target/app.exe"])

        creator = ReleaseCreator(
            make_config(publish=None, github_release=gh_config), tmp_path, dry_run=False
        )
        creator.create(internal=True)

        publish_call = mock_publisher_class.return_value.publish.call_args
        assert publish_call.kwargs["notes"] is None


class TestVersionNameBump:
    """A full release keeps its label and pubspec version in sync."""

    @staticmethod
    def version_file(root: Path, version: str = "1.1.0+1359") -> VersionFile:
        path = root / "pubspec.yaml"
        path.write_bytes(f"name: app\r\n  version: {version}\r\n\r\nother: x\r\n".encode())
        return VersionFile(path)

    @staticmethod
    def config(notes_format: str = "{build}", publish: str | None = None) -> CreateConfig:
        return make_config(
            publish=publish,
            label_format="{version}+{build}",
            notes_label_format=notes_format,
        )

    @staticmethod
    def bats(version_file: VersionFile, fail_on: str | None = None):
        def run(cmd: list[str], cwd: Path, dry_run: bool = False) -> None:
            if dry_run:
                return
            if fail_on and uses([cmd], fail_on):
                raise ReleaseCreateError(f"{fail_on} failed")
            if uses([cmd], "build_increment.bat"):
                version_file.bump()
            if uses([cmd], "build_decrement.bat"):
                version_file.bump(-1)

        return run

    @patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"])
    def test_labels_and_notes(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        creator = ReleaseCreator(
            self.config("{version}_{build}"), tmp_path, version_file=version_file
        )
        labels = creator._compute_labels()
        assert (labels.previous, labels.shipping, labels.notes) == (
            "1.1.0+1359",
            "1.1.1+1360",
            "1.1.1_1360",
        )
        assert labels.name_bump == VersionNameBump("1.1.0", "1.1.1")

    @patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"])
    def test_option_off_keeps_name(self, mock_capture: MagicMock, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        labels = ReleaseCreator(self.config(), tmp_path)._compute_labels()
        assert labels.shipping == "1.1.0+1360"
        assert labels.name_bump is None
        assert version_file.read().label == "1.1.0+1359"

    @pytest.mark.parametrize(
        ("internal", "keep", "expected"),
        [(False, False, "1.1.1+1360"), (True, False, "1.1.0+1360"), (False, True, "1.1.0+1360")],
    )
    def test_success_and_exceptions(
        self, tmp_path: Path, internal: bool, keep: bool, expected: str
    ) -> None:
        version_file = self.version_file(tmp_path)
        if not internal:
            prepare_notes(tmp_path, "1360")
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command", side_effect=self.bats(version_file)
            ) as run,
            patch("release_tool.release_creator.confirm", return_value=True) as confirm,
        ):
            creator = ReleaseCreator(
                self.config("{build}", "tools/publish.bat"), tmp_path, version_file=version_file
            )
            creator.create(internal=internal, keep_version_name=keep)
        assert version_file.read().label == expected
        assert (tmp_path / "tools/previous_version.txt").read_text().strip() == "1.1.0+1359"
        assert ["git", "tag", expected] in ran(run)
        assert ["git", "push", "origin", expected] in ran(run)
        assert f"Publish {expected} to Store? [y/N]" in [c.args[0] for c in confirm.call_args_list]

    def test_github_release_uses_bumped_tag(self, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        prepare_notes(tmp_path, "1360")
        gh_config = GitHubReleaseConfig(enabled=True, assets=["app.exe"], tag_format="v{label}")
        config = self.config()
        config.github_release = gh_config
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch("release_tool.release_creator.run_command", side_effect=self.bats(version_file)),
            patch("release_tool.release_creator.confirm", return_value=True),
            patch("release_tool.release_creator.GitHubPublisher") as publisher,
            patch("release_tool.release_creator.render_notes_markdown", return_value="notes"),
        ):
            ReleaseCreator(config, tmp_path, version_file=version_file).create()
        assert publisher.return_value.publish.call_args.args[0] == "v1.1.1+1360"

    @pytest.mark.parametrize("failed", ["translate.bat", "build.bat"])
    def test_failed_build_restores_bytes(self, tmp_path: Path, failed: str) -> None:
        version_file = self.version_file(tmp_path)
        original = version_file.path.read_bytes()
        prepare_notes(tmp_path, "1360")
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command",
                side_effect=self.bats(version_file, failed),
            ),
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(ReleaseCreateError, match="failed"):
                creator.create()
        assert version_file.path.read_bytes() == original

    def test_dry_run_keeps_bytes_and_reports_bumped_label(self, tmp_path: Path, caplog) -> None:
        version_file = self.version_file(tmp_path)
        original = version_file.path.read_bytes()
        prepare_notes(tmp_path, "1360")
        with (
            caplog.at_level(logging.INFO),
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch("release_tool.release_creator.run_command") as run,
        ):
            ReleaseCreator(
                self.config(), tmp_path, dry_run=True, version_file=version_file
            ).create()
        assert version_file.path.read_bytes() == original
        assert "Next release label: 1.1.1+1360" in caplog.text
        assert "[DRY RUN] Would set the version name" in caplog.text
        assert ["git", "tag", "1.1.1+1360"] in ran(run)

    @pytest.mark.parametrize(
        ("file_version", "get_version", "get_build", "error"),
        [
            ("1.1.0+1359", "1.1.0-beta", "1359", "non-numeric"),
            ("1.2.0+1359", "1.1.0", "1359", "1.2.0"),
            ("1.1.0+1358", "1.1.0", "1359", "1358"),
        ],
    )
    def test_mismatch_aborts_before_mutation(
        self, tmp_path: Path, file_version: str, get_version: str, get_build: str, error: str
    ) -> None:
        version_file = self.version_file(tmp_path, file_version)
        original = version_file.path.read_bytes()
        with (
            patch(
                "release_tool.release_creator.capture_command", side_effect=[get_version, get_build]
            ),
            patch("release_tool.release_creator.run_command") as run,
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(ReleaseCreateError, match=error):
                creator.create()
        run.assert_not_called()
        assert version_file.path.read_bytes() == original

    # PermissionError is what the real file write raises; it is not a ReleaseToolError.
    @pytest.mark.parametrize("error", [ConfigurationError, PermissionError])
    def test_failed_name_write_still_decrements_build(
        self, tmp_path: Path, error: type[Exception]
    ) -> None:
        version_file = self.version_file(tmp_path)
        original = version_file.path.read_bytes()
        prepare_notes(tmp_path, "1360")
        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command", side_effect=self.bats(version_file)
            ) as run,
            patch.object(version_file, "set_name", side_effect=error("name write failed")),
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(error, match="name write failed"):
                creator.create()
        assert uses(ran(run), "build_decrement.bat")
        assert version_file.path.read_bytes() == original

    def test_failed_name_restore_still_decrements_build(self, tmp_path: Path) -> None:
        version_file = self.version_file(tmp_path)
        prepare_notes(tmp_path, "1360")
        write_name = version_file.set_name

        def set_name(name: str) -> object:
            if name == "1.1.0":
                raise OSError("restore failed")
            return write_name(name)

        with (
            patch("release_tool.release_creator.capture_command", side_effect=["1.1.0", "1359"]),
            patch(
                "release_tool.release_creator.run_command",
                side_effect=self.bats(version_file, "build.bat"),
            ) as run,
            patch.object(version_file, "set_name", side_effect=set_name),
        ):
            creator = ReleaseCreator(self.config(), tmp_path, version_file=version_file)
            with pytest.raises(ReleaseCreateError, match="build.bat failed"):
                creator.create()
        assert uses(ran(run), "build_decrement.bat")
        assert version_file.read().label == "1.1.1+1359"
