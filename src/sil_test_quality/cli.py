"""!
@brief Command-line options and startup for precommit checks.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from .environment import HookEnvironment

HELP_DESCRIPTION = (
    "Run repository checks with brief, normal, or verbose evidence."
)


def main(root: Path | None = None) -> int:
    """!
    @brief Start the checks with the requested options.
    @details Normal output is the default. A startup failure replaces the old
    log when possible so a previous pass is not mistaken for the current result.
    @param root Default repo from the bootstrap. None uses the working
    directory. --root overrides it.
    @return Check exit status, or one if setup or execution fails.
    @throws SystemExit Argument parsing handles help or rejects invalid
    command-line arguments.
    """
    parser = argparse.ArgumentParser(description=HELP_DESCRIPTION)
    parser.add_argument("--root", type=Path, default=root or Path.cwd())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-v", "--verbose", action="store_true")
    mode.add_argument("--brief", action="store_true")
    mode.add_argument("--normal", action="store_true")
    parser.add_argument("--fix", action="store_true")
    options = parser.parse_args()
    root = options.root.resolve()
    try:
        return HookEnvironment(root).run(
            fix=options.fix, verbose=options.verbose, brief=options.brief
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        message = (
            f"Precommit FAILED: checks could not finish. {error}\n"
            "[NOT RUN] No complete quality report is available."
        )
        print(message, file=sys.stderr)
        try:
            log = root / "artifacts/precommit.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(message + "\n", encoding="utf-8")
        except OSError:
            pass
        print(f"Details: {root / 'artifacts/precommit-setup.log'}")
        return 1
