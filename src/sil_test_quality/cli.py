"""!
@brief Command-line options and startup for precommit checks.
"""

import subprocess
import sys
from pathlib import Path

import click

from .environment import HookEnvironment

HELP_DESCRIPTION = (
    "Run repository checks with brief, normal, or verbose evidence."
)


class QualityCommand(click.Command):
    """!
    @brief Command-line settings and execution for repository checks.
    """

    def __init__(self, root: Path | None = None) -> None:
        """!
        @brief Define the repository, repair and report options.
        @param root Default repo from the bootstrap. None uses the working
        directory. --root overrides it.
        """
        super().__init__(
            "sil-test-quality",
            params=[
                click.Option(
                    ["--root"],
                    type=click.Path(path_type=Path),
                    default=root or Path.cwd(),
                ),
                click.Option(["-v", "--verbose"], is_flag=True),
                click.Option(["--brief"], is_flag=True),
                click.Option(["--normal"], is_flag=True),
                click.Option(["--fix"], is_flag=True),
            ],
            callback=self.execute,
            help=HELP_DESCRIPTION,
            context_settings={"help_option_names": ["-h", "--help"]},
        )

    def execute(
        self, root: Path, verbose: bool, brief: bool, normal: bool, fix: bool
    ) -> int:
        """!
        @brief Run checks using the selected report mode.
        @details A startup failure replaces the old log when possible so a
        previous pass is not mistaken for the current result.
        @param root Repository whose source and configuration will be checked.
        @param verbose Show all check evidence.
        @param brief Show verdicts and final warnings only.
        @param normal Select the default report with truncated evidence.
        @param fix Repair imports and formatting before checking.
        @return Check exit status, or one if setup or execution fails.
        @throws click.UsageError More than one report mode was selected.
        """
        if sum((verbose, brief, normal)) > 1:
            raise click.UsageError(
                "Choose one report mode: --brief, --normal, or --verbose"
            )
        root = root.resolve()
        try:
            return HookEnvironment(root).run(
                fix=fix, verbose=verbose, brief=brief
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


def main(root: Path | None = None) -> int:
    """!
    @brief Start the command and preserve the checker's exit status.
    @param root Default repository supplied by the bootstrap, or None to use
    the working directory.
    @return Check exit status, or zero when displaying help.
    @throws SystemExit Command-line arguments are invalid.
    """
    try:
        return QualityCommand(root).main(standalone_mode=False)
    except click.ClickException as error:
        error.show()
        raise SystemExit(error.exit_code) from None
