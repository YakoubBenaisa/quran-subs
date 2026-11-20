"""Entry point of the packaged app (PyInstaller): same commands as `python -m quran_companion`."""
import sys

from quran_companion.__main__ import main

if __name__ == "__main__":
    args = sys.argv[1:]
    # started from the Start menu / Dock / app menu without arguments: open the settings window
    if not args or args[0].startswith("-psn_"):
        args = ["ui"]
    sys.exit(main(args))
