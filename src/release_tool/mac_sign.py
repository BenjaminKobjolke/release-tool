"""Sign, notarize and staple one `.app` or `.dmg` in place."""

import tempfile
from pathlib import Path

from .bat_runner import run_command
from .exceptions import MacPackageError
from .mac_config import DEFAULT_ENTITLEMENTS, MacSignConfig
from .mac_tools import (
    ASSESS,
    CODESIGN,
    ENTITLEMENTS,
    FORCE,
    OPTIONS_RUNTIME,
    SIGN,
    SPCTL,
    STAPLE,
    STAPLER,
    TIMESTAMP,
    TYPE,
    VALIDATE,
    XCRUN,
    AppLogger,
    notarize,
    require_macos,
)

logger = AppLogger(__name__)

APP_SUFFIX = ".app"
DMG_SUFFIX = ".dmg"
DEEP = "--deep"
DITTO = "ditto"
DITTO_CREATE = "-c"
DITTO_ZIP = "-k"
SEQUESTER_RSRC = "--sequesterRsrc"
KEEP_PARENT = "--keepParent"
EXECUTE = "execute"
OPEN = "open"
CONTEXT = "--context"
PRIMARY_SIGNATURE = "context:primary-signature"
VERY_VERBOSE = "-vv"
COMMAND_NAME = "mac-sign"


class MacSigner:
    """Sign one app bundle or disk image in place."""

    def __init__(self, config: MacSignConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run

    def sign(self, target: Path, entitlements: Path | None = None) -> Path:
        """Sign, notarize, staple and verify one `.app` bundle or `.dmg` image."""
        target = target.resolve()
        kind = self._kind(target)
        require_macos(COMMAND_NAME, self.dry_run)
        cwd = target.parent

        if kind == APP_SUFFIX:
            app_entitlements = DEFAULT_ENTITLEMENTS if entitlements is None else entitlements
            if not app_entitlements.is_file():
                raise MacPackageError(f"App entitlements file not found: {app_entitlements}")
            self._sign_app(target, app_entitlements, cwd)
        else:
            if entitlements is not None:
                logger.info("Ignoring --entitlements for .dmg target: %s", target)
            self._sign_dmg(target, cwd)

        logger.info("Signed macOS artifact: %s", target)
        return target

    def _kind(self, target: Path) -> str:
        """Validate the path and return its supported suffix."""
        suffix = target.suffix.lower()
        if suffix not in (APP_SUFFIX, DMG_SUFFIX):
            raise MacPackageError(
                f"Unsupported macOS signing target: {target}; expected an existing .app "
                "directory or .dmg file"
            )
        if not target.exists():
            raise MacPackageError(f"Mac signing target not found: {target}")
        if suffix == APP_SUFFIX and not target.is_dir():
            raise MacPackageError(f"App bundle must be an existing directory: {target}")
        if suffix == DMG_SUFFIX and not target.is_file():
            raise MacPackageError(f"Disk image must be an existing file: {target}")
        return suffix

    def _sign_app(self, app: Path, entitlements: Path, cwd: Path) -> None:
        """Sign an app, notarize a temporary archive, then staple and verify it."""
        run_command(
            [
                CODESIGN,
                DEEP,
                FORCE,
                OPTIONS_RUNTIME,
                TIMESTAMP,
                ENTITLEMENTS,
                str(entitlements),
                SIGN,
                self.config.app_identity,
                str(app),
            ],
            cwd=cwd,
            dry_run=self.dry_run,
        )
        with tempfile.TemporaryDirectory(prefix="release-tool-mac-sign-") as temp_dir:
            archive = Path(temp_dir) / f"{app.stem}.zip"
            run_command(
                [
                    DITTO,
                    DITTO_CREATE,
                    DITTO_ZIP,
                    SEQUESTER_RSRC,
                    KEEP_PARENT,
                    str(app),
                    str(archive),
                ],
                cwd=cwd,
                dry_run=self.dry_run,
            )
            notarize(archive, self.config.keychain_profile, cwd, self.dry_run)
        self._staple_and_verify(app, [EXECUTE], cwd)

    def _sign_dmg(self, dmg: Path, cwd: Path) -> None:
        """Sign and notarize a disk image, then staple and verify it."""
        run_command(
            [CODESIGN, FORCE, TIMESTAMP, SIGN, self.config.app_identity, str(dmg)],
            cwd=cwd,
            dry_run=self.dry_run,
        )
        notarize(dmg, self.config.keychain_profile, cwd, self.dry_run)
        self._staple_and_verify(dmg, [OPEN, CONTEXT, PRIMARY_SIGNATURE], cwd)

    def _staple_and_verify(self, target: Path, spctl_args: list[str], cwd: Path) -> None:
        """Staple Apple's ticket and verify it with stapler and Gatekeeper."""
        commands = (
            [XCRUN, STAPLER, STAPLE, str(target)],
            [XCRUN, STAPLER, VALIDATE, str(target)],
            [SPCTL, ASSESS, TYPE, *spctl_args, VERY_VERBOSE, str(target)],
        )
        for command in commands:
            run_command(command, cwd=cwd, dry_run=self.dry_run)
