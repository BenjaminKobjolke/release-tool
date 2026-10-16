"""Integration coverage for the mac-sign CLI dry run."""

from pathlib import Path

import pytest

from release_tool import mac_config
from release_tool.cli import main


def test_dry_run_logs_app_and_dmg_steps(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI loads shared signing values and previews both target workflows."""
    signing = tmp_path / "mac_signing.ini"
    signing.write_text(
        "[MacSigning]\napp_identity = App Identity\nkeychain_profile = test-profile\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mac_config, "MAC_SIGNING_FILE", signing)
    app = tmp_path / "fman.app"
    app.mkdir()
    dmg = tmp_path / "fman.dmg"
    dmg.touch()

    with caplog.at_level("INFO"):
        assert main(["mac-sign", str(app), "--dry-run"]) == 0
        app_log = caplog.text
        caplog.clear()
        assert main(["mac-sign", str(dmg), "--dry-run"]) == 0
        dmg_log = caplog.text

    for command in ("codesign", "ditto", "notarytool", "stapler", "spctl"):
        assert command in app_log
    assert "ditto" not in dmg_log
    for command in ("codesign", "notarytool", "stapler", "spctl"):
        assert command in dmg_log
