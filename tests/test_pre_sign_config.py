"""Tests for pre-signing configuration parsing."""

from pathlib import Path

import pytest

from release_tool.config import ReleaseConfig
from release_tool.exceptions import ConfigurationError
from release_tool.pre_signer import PreSignMethod


class TestPreSignConfigCharacterization:
    """Pin today's network pre-signing parser behavior before extending it."""

    @staticmethod
    def _write_config(tmp_path: Path, presigning: str = "") -> Path:
        path = tmp_path / "config.ini"
        path.write_text(
            "[FTP]\nhost = ftp.example.com\nusername = testuser\npassword = testpass\n"
            + presigning
        )
        return path

    def test_no_presigning_section_returns_none(self, tmp_path: Path) -> None:
        config = ReleaseConfig.from_ini_file(self._write_config(tmp_path))

        assert config.pre_sign is None

    def test_disabled_presigning_returns_none(self, tmp_path: Path) -> None:
        config = ReleaseConfig.from_ini_file(
            self._write_config(tmp_path, "\n[PreSigning]\nenabled = false\n")
        )

        assert config.pre_sign is None

    def test_enabled_network_presigning_keeps_defaults(self, tmp_path: Path) -> None:
        config = ReleaseConfig.from_ini_file(
            self._write_config(
                tmp_path,
                "\n[PreSigning]\nenabled = true\n"
                "network_path = \\\\server\\unsigned\n"
                "network_path_signed = \\\\server\\signed\n"
                "expected_signer = Example GmbH\n",
            )
        )

        assert config.pre_sign is not None
        assert config.pre_sign.network_path == "\\\\server\\unsigned"
        assert config.pre_sign.network_path_signed == "\\\\server\\signed"
        assert config.pre_sign.expected_signer == "Example GmbH"
        assert config.pre_sign.poll_interval == 10
        assert config.pre_sign.timeout == 300

    @pytest.mark.parametrize(
        ("missing", "message"),
        [
            ("network_path", "PreSigning network_path is required when enabled"),
            (
                "network_path_signed",
                "PreSigning network_path_signed is required when enabled",
            ),
            ("expected_signer", "PreSigning expected_signer is required when enabled"),
        ],
    )
    def test_enabled_network_presigning_requires_each_key(
        self, tmp_path: Path, missing: str, message: str
    ) -> None:
        values = {
            "network_path": "\\\\server\\unsigned",
            "network_path_signed": "\\\\server\\signed",
            "expected_signer": "Example GmbH",
        }
        del values[missing]
        section = "\n[PreSigning]\nenabled = true\n" + "".join(
            f"{key} = {value}\n" for key, value in values.items()
        )

        with pytest.raises(ConfigurationError, match=message):
            ReleaseConfig.from_ini_file(self._write_config(tmp_path, section))


class TestPreSignMethodConfig:
    """Validate the network and remote method INI variants."""

    @staticmethod
    def _write_config(tmp_path: Path, presigning: str) -> Path:
        path = tmp_path / "config.ini"
        path.write_text(
            "[FTP]\nhost = ftp.example.com\nusername = testuser\npassword = testpass\n"
            + presigning
        )
        return path

    def test_method_defaults_to_network(self, tmp_path: Path) -> None:
        config = ReleaseConfig.from_ini_file(
            self._write_config(
                tmp_path,
                "\n[PreSigning]\nenabled = true\n"
                "network_path = \\\\server\\unsigned\n"
                "network_path_signed = \\\\server\\signed\n"
                "expected_signer = Example GmbH\n",
            )
        )

        assert config.pre_sign is not None
        assert config.pre_sign.method is PreSignMethod.NETWORK

    def test_remote_method_needs_only_signer_dir_and_expected_signer(
        self, tmp_path: Path
    ) -> None:
        config = ReleaseConfig.from_ini_file(
            self._write_config(
                tmp_path,
                "\n[PreSigning]\nenabled = true\nmethod = remote\n"
                "signer_dir = D:\\Tools\\SafeNet Signer\n"
                "expected_signer = Example GmbH\n"
                "network_path = ignored\nnetwork_path_signed = ignored\n"
                "poll_interval = ignored\ntimeout = ignored\n",
            )
        )

        assert config.pre_sign is not None
        assert config.pre_sign.method is PreSignMethod.REMOTE
        assert config.pre_sign.signer_dir == "D:\\Tools\\SafeNet Signer"
        assert config.pre_sign.network_path == ""
        assert config.pre_sign.network_path_signed == ""

    @pytest.mark.parametrize(
        ("values", "message"),
        [
            ("expected_signer = Example GmbH\n", "signer_dir"),
            (
                "signer_dir = D:\\Tools\\signer\n",
                "expected_signer",
            ),
        ],
    )
    def test_remote_method_requires_remote_keys(
        self, tmp_path: Path, values: str, message: str
    ) -> None:
        section = "\n[PreSigning]\nenabled = true\nmethod = remote\n" + values

        with pytest.raises(ConfigurationError, match=message):
            ReleaseConfig.from_ini_file(self._write_config(tmp_path, section))

    def test_unknown_method_names_valid_values(self, tmp_path: Path) -> None:
        section = "\n[PreSigning]\nenabled = true\nmethod = ftp\n"

        with pytest.raises(ConfigurationError, match="network.*remote"):
            ReleaseConfig.from_ini_file(self._write_config(tmp_path, section))

    def test_method_is_case_insensitive(self, tmp_path: Path) -> None:
        config = ReleaseConfig.from_ini_file(
            self._write_config(
                tmp_path,
                "\n[PreSigning]\nenabled = true\nmethod = Remote\n"
                "signer_dir = D:\\Tools\\signer\nexpected_signer = Example GmbH\n",
            )
        )

        assert config.pre_sign is not None
        assert config.pre_sign.method is PreSignMethod.REMOTE
