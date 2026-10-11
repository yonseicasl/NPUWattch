"""The console banner of the NPUWattch CLI."""

from npuwattch import __version__

_BANNER = r"""
   ______  ______  _     _ _   _   _                     _
  |  ___ \(_____ \| |   | | | | | | |      _   _        | |
  | |   | |_____) ) |   | | | | | | | ____| |_| |_  ____| |__
  | |   | |  ____/| |   | | | | | | |/ _  |  _)  _)/ ___)  _ \
  | |   | | |     | |___| | |_| |_| ( ( | | |_| |_( (___| | | |
  |_|   |_|_|      \______|\________|\_||_|\___)___)____)_| |_|
"""


def print_banner() -> None:
    """Print the NPUWattch banner and the version line."""
    print(_BANNER)
    print(f"                         NPUWattch v{__version__}                ")  # nw-lint: text
    print ("2025-2026 Yonsei University Computer Architecture and Systems Lab")  # nw-lint: text
    print ("                     ikamusume@yonsei.ac.kr                      ")  # nw-lint: text
    print ()
    print ()
