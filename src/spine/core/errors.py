"""Shared Spine exception types."""

from dataclasses import dataclass


class SpineError(Exception):
    """Base exception for Spine runtime errors."""


@dataclass
class SpineValidationError(SpineError):
    """Validation failure with a stable machine-readable code.

    Exceptions must permit traceback assignment by transaction context managers.
    """

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
