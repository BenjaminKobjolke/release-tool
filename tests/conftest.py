"""Pytest fixtures for release tool tests."""

import pytest
from pathlib import Path
import tempfile

from release_tool.config import (
    FTPConfig,
    OldFileConfig,
    OldFilePolicy,
    ReleaseConfig,
    SubfolderNaming,
)


@pytest.fixture
def ftp_config() -> FTPConfig:
    """Create a test FTP configuration."""
    return FTPConfig(
        host="ftp.example.com",
        port=21,
        username="testuser",
        password="testpass",
        remote_path="/releases",
    )


@pytest.fixture
def old_file_config_delete() -> OldFileConfig:
    """Create a test old file config with delete policy."""
    return OldFileConfig(
        policy=OldFilePolicy.DELETE,
        subfolder_base="old_versions",
        subfolder_naming=SubfolderNaming.TIMESTAMP,
    )


@pytest.fixture
def old_file_config_rename() -> OldFileConfig:
    """Create a test old file config with rename policy."""
    return OldFileConfig(
        policy=OldFilePolicy.RENAME,
        subfolder_base="old_versions",
        subfolder_naming=SubfolderNaming.TIMESTAMP,
    )


@pytest.fixture
def release_config(ftp_config: FTPConfig, old_file_config_delete: OldFileConfig) -> ReleaseConfig:
    """Create a test release configuration."""
    return ReleaseConfig(ftp=ftp_config, old_file=old_file_config_delete)


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file."""
    config_content = """[FTP]
host = ftp.example.com
port = 21
username = testuser
password = testpass
remote_path = /releases

[OldFileHandling]
policy = rename
subfolder_base = old_versions
subfolder_naming = timestamp
"""
    config_path = tmp_path / "config.ini"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def temp_file(tmp_path: Path) -> Path:
    """Create a temporary file to upload."""
    file_path = tmp_path / "test_app.exe"
    file_path.write_bytes(b"test content")
    return file_path
