"""!
@brief Console output and saved evidence for precommit reports.
"""

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .activity import CheckActivity
from .reports.diagnostics import DiagnosticReport
from .table import ReportTable


class CheckOutput:
    """!
    @brief Collect check results and produce console and log output.
    @details Use as a context manager for one run. Start a section, add
    evidence, then record its result. Stop the live header before printing other
    console output. Writes are not synchronized between callers.
    """

    def __init__(
        self,
        root: Path,
        verbose: bool = False,
        filename: str = "precommit.log",
        *,
        brief: bool = False,
    ) -> None:
        """!
        @brief Set the report destination and console detail level.
        @param root Repo used as the tool working directory and location for
        artifacts.
        @param verbose True to print full evidence instead of the normal
        shortened view.
        @param filename Log name under artifacts. Defaults to precommit.log.
        @param brief True to hide check evidence and keep verdicts and the final
        summary.
        """

        self.root = root
        self.verbose = verbose
        self.brief = brief
        self.path = root / "artifacts" / filename
        self.failures: list[str] = []
        self.results: dict[str, str] = {}
        self.pending: list[str] = []
        self.normal: list[str] = []
        self.advisories: dict[str, list[str]] = {}
        self.table = ReportTable()
        self.activity = CheckActivity()

    def __enter__(self) -> "CheckOutput":
        """!
        @brief Open a fresh report log.
        @return This recorder, assigned by the with statement for checks to use.
        """

        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The context manager closes this stream in __exit__.
        self.log = self.path.open("w", encoding="utf-8")  # noqa: SIM115
        return self

    def __exit__(self, *exception: object) -> None:
        """!
        @brief Report any unfinished section and close the log.
        @param exception Exception type, value and traceback from the with
        block. These are accepted but not suppressed.
        """

        if self.pending or self.activity.label:
            self.section(
                self.activity.label or "Incomplete", "ERROR", always=True
            )
        self.log.close()

    def start(self, label: str) -> None:
        """!
        @brief Show the header for a check that is starting.
        @param label Check name used for the running header and its later
        result.
        """
        self.activity.start(label)

    def detail(
        self, text: str, *, normal: str | None = None, literal: bool = False
    ) -> None:
        """!
        @brief Collect evidence for the current report section.
        @details Queues text until section prints the selected view and writes
        the full view to the log.
        @param text Full check evidence to retain for verbose output and
        logging.
        @param normal Shortened evidence for normal output. None uses text
        unchanged.
        @param literal True to preserve table/subsection layout. False adds
        evidence bullets.
        """

        for content, target in (
            (text, self.pending),
            (text if normal is None else normal, self.normal),
        ):
            if content:
                target.append(
                    "\n" + content if literal else self.table.bullets(content)
                )

    def section(self, label: str, status: str, *, always: bool = False) -> None:
        """!
        @brief Print and save one completed report block.
        @details Stops the running indicator, flushes the full block to the log
        and clears the evidence for the next section.
        @param label Section name shown at the left of the header.
        @param status Result text shown on the right. May be empty for a plain
        heading.
        @param always True to show this section's evidence even in brief mode.
        """
        active = self.activity.stop()
        full = "\n".join(self.table.render(label, status, self.pending))
        self.log.write(full + "\n")
        self.log.flush()
        body = self.pending if self.verbose else self.normal
        if self.brief and not always:
            body = []
        visible = list(self.table.render(label, status, body))
        print(
            "\r" + "\n".join(visible[1:]) if active else "\n".join(visible),
            flush=True,
        )
        self.pending.clear()
        self.normal.clear()

    @staticmethod
    def tool_name(command: list[str]) -> str:
        """!
        @brief Identify the tool from the command being run.
        @param command Executable and arguments passed to the subprocess.
        @return Python module name or executable filename. Coverage runs also
        include the target module when launched with -m.
        """
        name = Path(command[0].replace("\\", "/")).name
        arguments = command[1:]
        if re.fullmatch(
            r"(?:pythonw?|pypy|py)(?:\d+(?:\.\d+)*)?(?:\.exe)?", name.lower()
        ):
            module, arguments = CheckOutput._module(arguments)
            name = module or name
        if name in ("coverage", "coverage.exe") and arguments[:1] == ["run"]:
            target, _ = CheckOutput._module(arguments[1:])
            if target:
                name += f" / {target}"
        return name

    @staticmethod
    def _module(arguments: list[str]) -> tuple[str, list[str]]:
        """!
        @brief Find a Python -m target without reading the target's arguments.
        @param arguments Arguments following the Python executable or coverage
        run command.
        @return Module name and its remaining arguments, or empty values when
        the command does not launch a module.
        """
        remaining = iter(arguments)
        for argument in remaining:
            if argument == "-m":
                return next(remaining, ""), list(remaining)
            if argument in ("-W", "-X"):
                next(remaining, None)
            elif argument in ("-c", "--") or not argument.startswith("-"):
                break
        return "", []

    def command(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        *,
        options: Sequence[str] = (),
        view: Callable[[str], tuple[str, str]] | None = None,
        literal: bool = False,
    ) -> int:
        """!
        @brief Run a tool and collect its output for the report.
        @param command Executable and argument list built by the check, run
        without a shell.
        @param env Child environment variables. None inherits the current
        environment.
        @param options Extra command arguments, also shown in the report.
        @param view Function converting captured output to full/normal strings.
        Defaults to DiagnosticReport.
        @param literal True to keep native table layout in the captured output.
        @return Tool exit code for the check to evaluate, or one if the tool
        cannot start.
        """

        command = [*command, *options]
        tool = self.tool_name(command)
        environment = dict(os.environ if env is None else env)
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["NO_COLOR"] = "1"
        environment["PY_COLORS"] = "0"
        try:
            result = subprocess.run(
                command,
                cwd=self.root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            full, normal = (view or DiagnosticReport().render)(
                result.stdout or ""
            )
            if full:
                separator = "\n" if literal else " "
                self.detail(
                    f"{tool} output:{separator}{full}",
                    normal=f"{tool} output:{separator}{normal}",
                    literal=literal,
                )
            status = result.returncode
        except OSError as error:
            self.detail(str(error))
            status = 1
        self._command_details(command, tool, options, status)
        return status

    def _command_details(
        self, command: list[str], tool: str, options: Sequence[str], status: int
    ) -> None:
        """!
        @brief Record which tool ran and the arguments it received.
        @param command Complete subprocess command, including options.
        @param tool Name derived from the executable and module arguments.
        @param options Arguments appended by command and included as evidence.
        @param status Tool exit code, or one if it could not run.
        """
        self.detail(f"- Tool: {tool}")
        if command[0] == sys.executable:
            for package in tool.split(" / "):
                try:
                    installed = version(package)
                except PackageNotFoundError:
                    installed = "unavailable"
                self.detail(f"- Version: {package} {installed}")
        else:
            self.detail("- Version: unavailable for this executable")
        if options:
            self.detail(f"- Options: {shlex.join(options)}")
        self.detail(f"- Exit status: {status}")

    def result(self, label: str, passed: bool) -> None:
        """!
        @brief Record and display whether a required check passed.
        @param label Check name for its section and the final failure list.
        @param passed The check's decision. False records a blocking failure.
        """

        self._record(label, "PASS" if passed else "FAIL")
        if not passed:
            self.failures.append(label)

    def warning(self, label: str, details: list[str]) -> None:
        """!
        @brief Record warnings without blocking the commit.
        @param label Advisory name used in the final Warnings section.
        @param details Warning messages to display. An empty list records a
        passing advisory.
        """

        self.results[label] = "WARNING" if details else "PASS"
        self.advisories[label] = details

    def _record(self, label: str, status: str) -> None:
        """!
        @brief Save a verdict and print the section evidence.
        @param label Check name passed by result for the saved verdict and
        header.
        @param status PASS or FAIL text chosen by result.
        """

        self.results[label] = status
        self.section(label, status)

    def finish(self) -> int:
        """!
        @brief Print the final result and warnings.
        @return One if any required check failed, otherwise zero. Warnings alone
        do not fail the commit.
        """

        if self.failures:
            self.detail("Failed sections:", literal=True)
            for label in self.failures:
                self.detail(f"- {label}")
            self.detail("Verbose: git hook run pre-commit -- --verbose")
        self.section("Result", "FAIL" if self.failures else "PASS", always=True)
        for label, details in self.advisories.items():
            self.detail(f"- {label}: {', '.join(details) if details else '0'}")
        for label, status in self.results.items():
            if status == "NOT RUN":
                self.detail(f"- {label}: NOT RUN")
        warnings = any(self.advisories.values()) or "NOT RUN" in (
            self.results.values()
        )
        if not self.advisories and not warnings:
            self.detail("- None")
        status = "WARNING" if warnings else "PASS"
        self.section("Warnings", status, always=True)
        return int(bool(self.failures))
