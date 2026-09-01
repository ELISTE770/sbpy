"""Entry point runner for SBpy standalone executable and packaging."""

import sys
from sbpy.cli import main

if __name__ == "__main__":
    sys.exit(main())
