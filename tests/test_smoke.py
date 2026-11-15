"""Smoke test that the package imports."""

import residency_match


def test_package_imports() -> None:
    """The package imports and exposes a version string."""
    assert residency_match.__version__
