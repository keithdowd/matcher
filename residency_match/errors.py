"""Exception hierarchy for the residency match simulator.

This module only defines exception classes. It does no I/O and does not decide
how errors are shown; the command-line layer maps each exception to an exit
status using the ``exit_code`` attribute.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Imported only for type hints: models.py imports this module at runtime.
    from residency_match.models import ValidationIssue


class ResidencyMatchError(Exception):
    """Base class for every error this package raises on purpose.

    Attributes
    ----------
    exit_code : int
        Process exit status the command-line layer uses for this error.
    """

    exit_code: int = 1


class InputError(ResidencyMatchError):
    """Raised when input files fail validation.

    Parameters
    ----------
    issues : Sequence[ValidationIssue]
        Every problem found, so the user can fix them all in one pass.

    Attributes
    ----------
    issues : tuple[ValidationIssue, ...]
        The problems found, in the order they were detected.
    exit_code : int
        Always 2.
    """

    exit_code = 2

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        """Store the issues and build a one-line summary message."""
        self.issues: tuple[ValidationIssue, ...] = tuple(issues)
        super().__init__(f"{len(self.issues)} input problem(s) found")


class UsageError(ResidencyMatchError):
    """Raised for bad command-line usage or invalid generator parameters.

    Attributes
    ----------
    exit_code : int
        Always 3.
    """

    exit_code = 3
