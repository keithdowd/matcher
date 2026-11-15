"""Entry point for ``python -m residency_match``.

Only calls :func:`residency_match.cli.main`; it contains no logic.
"""

import sys

from residency_match.cli import main

if __name__ == "__main__":
    sys.exit(main())
