"""quran-companion [ui | overlay [opts] | toggle | cmd <command> | <command>]

  ui                         settings window
  overlay [--surah N] [--ayah N] [--mode recite|memorize|manual] [--hidden]
  toggle                     start the overlay, or quit it if running
  install-desktop            add / refresh the app-menu entry
  cmd next|prev|pause|hide|bigger|smaller|nextsurah|prevsurah|play|restyle|quit
  cmd surah 36 [ayah]  ·  cmd visible 0|1
Older forms (`next`, `surah 36`, `--surah 18`) keep working.
"""
import sys

from .ipc.protocol import parse_cli


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(__doc__); return 0
    from . import app
    if not args or args[0].startswith("-"):
        return app.run_overlay(args)
    head, rest = args[0], args[1:]
    if head == "ui": return app.run_ui()
    if head == "overlay": return app.run_overlay(rest)
    if head == "toggle": return app.run_toggle()
    if head == "install-desktop": return app.install_desktop_entry()
    if head == "cmd": return app.run_command(rest)
    if parse_cli(args) is not None: return app.run_command(args)
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
