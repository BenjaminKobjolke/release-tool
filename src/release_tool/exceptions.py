"""Custom exceptions for release tool."""


class ReleaseToolError(Exception):
    """Base exception for release tool errors."""


class ConfigurationError(ReleaseToolError):
    """Raised when configuration parsing fails."""


class FTPError(ReleaseToolError):
    """Raised when FTP operations fail."""


class PreSignError(ReleaseToolError):
    """Raised when pre-signing operations fail."""


class VersionExistsError(ReleaseToolError):
    """Raised when backup version folder already exists on remote."""
