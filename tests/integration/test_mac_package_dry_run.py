"""Integration coverage for the mac-package CLI dry run."""

from pathlib import Path

import pytest

from release_tool import mac_config
from release_tool.cli import main


def test_dry_run_resolves_config_and_logs_all_steps(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI resolves signing/version inputs without executing Mac commands."""
    binary = tmp_path / "tool"
    binary.write_bytes(b"fake executable")
    (tmp_path / "version.txt").write_text("3.4.5\n", encoding="utf-8")
    (tmp_path / "mac_signing.ini").write_text(
        """[MacSigning]
app_identity = App Identity
installer_identity = Installer Identity
keychain_profile = test-profile
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(mac_config, "MAC_SIGNING_FILE", tmp_path / "mac_signing.ini")
    config = tmp_path / "mac_package.ini"
    config.write_text(
        """[MacPackage]
identifier = com.example.tool
install_location = /usr/local/bin/tool
version_file = version.txt
output = dist/tool-{version}.pkg
""",
        encoding="utf-8",
    )

    with caplog.at_level("INFO"):
        result = main(
            ["mac-package", str(binary), str(config), "--project-root", str(tmp_path), "--dry-run"]
        )

    assert result == 0
    for command in ("codesign", "pkgbuild", "notarytool", "stapler", "pkgutil", "spctl"):
        assert command in caplog.text
    assert "3.4.5" in caplog.text
    assert str(tmp_path / "dist" / "tool-3.4.5.pkg") in caplog.text
