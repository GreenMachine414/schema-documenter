"""Start the GUI, or the command line when arguments are given."""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main
        return cli_main(sys.argv[1:])
    from .gui import main as gui_main
    return gui_main()
