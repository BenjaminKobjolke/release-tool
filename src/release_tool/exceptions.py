"""Custom exceptions for release tool."""


class ReleaseToolError(Exception):
    """Base exception for release tool errors."""


class ConfigurationError(ReleaseToolError):
    """Raised when configuration parsing fails."""


class FTPError(ReleaseToolError):
    """Raised when FTP operations fail."""
