"""Read-only checks for named FTP profiles."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import FTPConfig, build_ftp_config, load_parser
from .exceptions import ConfigurationError, FTPError
from .ftp_client import FTPClient

DEFAULT_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class ProfileCheckResult:
    """Result of checking one named FTP profile."""

    name: str
    ok: bool
    detail: str


def check_profiles(
    path: Path,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client_factory: Callable[[FTPConfig], FTPClient] = FTPClient,
) -> list[ProfileCheckResult]:
    """Check every profile's credentials and remote folder without changing the server."""
    parser = load_parser(path)
    names = parser.sections()
    if not names:
        raise ConfigurationError(f"No FTP profiles in {path}")

    results: list[ProfileCheckResult] = []
    for name in names:
        try:
            config = build_ftp_config(dict(parser[name]))
        except ConfigurationError as e:
            results.append(ProfileCheckResult(name, False, str(e)))
            continue

        try:
            client_factory(config).probe(timeout)
        except FTPError as e:
            detail = str(e)
            if config.password:
                detail = detail.replace(config.password, "[redacted]")
            results.append(ProfileCheckResult(name, False, detail))
        else:
            results.append(
                ProfileCheckResult(
                    name,
                    True,
                    f"{config.host}:{config.port} {config.remote_path}",
                )
            )

    return results
