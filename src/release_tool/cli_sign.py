"""CLI entry point for signing one file with a named signing profile."""

import argparse
import configparser
import logging
from pathlib import Path

from .cli_support import guarded, setup_logging
from .config import SIGNING_PROFILES_FILE, _parse_pre_sign_config
from .exceptions import ConfigurationError
from .release_manager import _create_pre_signer


def parse_sign_args(args: list[str]) -> argparse.Namespace:
    """Parse arguments for the sign subcommand."""
    parser = argparse.ArgumentParser(
        prog="release-tool sign",
        description="Sign one file with a signing profile, without uploading it",
    )
    parser.add_argument("file", type=Path, help="Path to the file to sign")
    parser.add_argument("profile", help="Section name in signing_profiles.ini")
    parser.add_argument(
        "--profiles",
        type=Path,
        default=SIGNING_PROFILES_FILE,
        help="Path to the signing profiles INI "
        "(default: signing_profiles.ini in the release-tool checkout)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def run_sign(args: list[str]) -> int:
    """Sign the file in place and verify its signer."""
    parsed = parse_sign_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    def action() -> bool:
        if not parsed.file.is_file():
            raise ConfigurationError(f"File not found: {parsed.file}")
        parser = configparser.ConfigParser()
        parser.read_dict({"PreSigning": {"profile": parsed.profile}})
        config = _parse_pre_sign_config(parser, parsed.profiles)
        signer = _create_pre_signer(config)
        if signer is None:
            raise ConfigurationError(f"Signing profile '{parsed.profile}' is not enabled")
        signer.process(parsed.file)
        logger.info(f"Signed: {parsed.file}")
        return True

    return guarded(logger, action)
