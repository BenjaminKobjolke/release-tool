"""Windows integration tests for the remote signer batch contract."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from release_tool.exceptions import PreSignError
from release_tool.pre_signer import PreSignConfig, PreSignMethod
from release_tool.remote_pre_signer import RemotePreSigner

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="signer contract uses sign.bat")


def _signer(tmp_path: Path, body: str) -> tuple[RemotePreSigner, Path, Path]:
    signer_dir = tmp_path / "SafeNet Signer"
    signer_dir.mkdir()
    signer_bat = signer_dir / "sign.bat"
    signer_bat.write_text("@echo off\n" + body, encoding="utf-8")
    file_path = tmp_path / "release file.exe"
    file_path.write_text("unsigned", encoding="utf-8")
    config = PreSignConfig(
        enabled=True,
        expected_signer="Example GmbH",
        method=PreSignMethod.REMOTE,
        signer_dir=str(signer_dir),
    )
    return RemotePreSigner(config), signer_bat, file_path


def test_remote_signer_streams_progress_and_verifies_signed_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    body = (
        'if not "%SIGNER_NO_PAUSE%"=="1" exit /b 1\n'
        'if not "%PYTHONUNBUFFERED%"=="1" exit /b 1\n'
        "echo Upload 50%%\n"
        "echo Download 100%%\n"
        'echo signed>"%~1"\n'
        "exit /b 0\n"
    )
    signer, _, file_path = _signer(tmp_path, body)
    caplog.set_level("INFO")

    with patch(
        "release_tool.remote_pre_signer.read_signer_name", return_value="Example GmbH"
    ) as read:
        result = signer.process(file_path)

    assert result == file_path
    assert file_path.read_text(encoding="utf-8").strip() == "signed"
    assert "Signer: Upload 50%" in caplog.text
    assert "Signer: Download 100%" in caplog.text
    read.assert_called_once_with(file_path.resolve())


@pytest.mark.parametrize(
    ("code", "meaning"),
    [
        (1, "config.json"),
        (2, "server reported"),
        (3, "timed out waiting"),
        (4, "connection or transfer"),
        (7, "unexpected"),
    ],
)
def test_nonzero_exit_has_contract_meaning(
    tmp_path: Path, code: int, meaning: str
) -> None:
    signer, _, file_path = _signer(tmp_path, f"exit /b {code}\n")

    with (
        patch("release_tool.remote_pre_signer.read_signer_name") as read,
        pytest.raises(PreSignError, match=f"exit code {code}.*{meaning}"),
    ):
        signer.process(file_path)

    read.assert_not_called()


@pytest.mark.parametrize("actual", ["Other GmbH", None])
def test_remote_signer_rejects_wrong_or_missing_signature(
    tmp_path: Path, actual: str | None
) -> None:
    signer, _, file_path = _signer(tmp_path, "exit /b 0\n")

    with (
        patch("release_tool.remote_pre_signer.read_signer_name", return_value=actual),
        pytest.raises(PreSignError, match="Example GmbH.*(Other GmbH|unsigned)"),
    ):
        signer.process(file_path)


def test_missing_sign_bat_reports_expected_path(tmp_path: Path) -> None:
    signer_dir = tmp_path / "Missing Signer"
    config = PreSignConfig(
        enabled=True,
        expected_signer="Example GmbH",
        method=PreSignMethod.REMOTE,
        signer_dir=str(signer_dir),
    )
    signer = RemotePreSigner(config)

    with pytest.raises(PreSignError, match="sign.bat") as error:
        signer.process(tmp_path / "release.exe")

    assert str(signer_dir / "sign.bat") in str(error.value)
