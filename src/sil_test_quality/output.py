"""!
@brief Console output and saved evidence for precommit reports.
"""

import os
import platform
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
        width: int = ReportTable.DEFAULT_WIDTH,
        wrap: bool = False,
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
        @param width Report columns, or zero for unframed text without wrapping.
        @param wrap Wrap console lines. The saved log always keeps full text.
        """

        self.root = root
        self.verbose = verbose
        self.brief = brief
        self.path = root / "artifacts" / filename
        self.failures: list[str] = []
        self.results: dict[str, str] = {}
        self.pending: list[str] = []
        self.normal: list[str] = []
        self.tools: set[str] = set()
        self.advisories: dict[str, list[str]] = {}
        self.deferred: dict[str, tuple[str, list[str]] | None] = {}
        self.table = ReportTable(width, wrap=wrap)
        self.log_table = ReportTable(width, wrap=True)
        self.activity = CheckActivity(self.table)

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
        self.release()
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
        @details Stops the running indicator and clears the evidence for the
        next section. Deferred blocks are held until release.
        @param label Section name shown at the left of the header.
        @param status Result text shown on the right. May be empty for a plain
        heading.
        @param always True to show this section's evidence even in brief mode.
        """
        deferred = label in self.deferred
        active = self.activity.stop(discard=deferred)
        full = "\n".join(self.log_table.render(label, status, self.pending))
        body = self.pending if self.verbose else self.normal
        if self.brief and not always:
            body = []
        visible = list(self.table.render(label, status, body))
        if deferred:
            self.deferred[label] = (full, visible)
        else:
            self._write(full, visible, active=active)
        self.pending.clear()
        self.normal.clear()
        self.tools.clear()

    def defer(self, *labels: str) -> None:
        """!
        @brief Hold completed blocks for display in the requested order.
        @param labels Section names in display order. Checks still execute in
        their original order and keep their running indicators.
        """
        self.deferred.update(dict.fromkeys(labels))

    def release(self) -> None:
        """!
        @brief Print held blocks without changing their evidence or verdicts.
        """
        for block in self.deferred.values():
            if block is not None:
                self._write(*block)
        self.deferred.clear()

    def _write(
        self, full: str, visible: list[str], *, active: bool = False
    ) -> None:
        """!
        @brief Save the full block and print the selected console view.
        @param full Complete evidence formatted for the saved log.
        @param visible Rows selected for the current console detail level.
        @param active True to replace a running header already on screen.
        """
        self.log.write(full + "\n\n")
        self.log.flush()
        if active:
            visible = visible[1:] if self.table.width else visible
            visible[0] = "\r" + visible[0]
        print(
            "\n".join(visible), end="\n" if self.brief else "\n\n", flush=True
        )

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
        if CheckOutput.is_python(command[0]):
            module, arguments = CheckOutput._module(arguments)
            name = module or name
        if name in ("coverage", "coverage.exe") and arguments[:1] == ["run"]:
            target, _ = CheckOutput._module(arguments[1:])
            if target:
                name += f" / {target}"
        return name

    @staticmethod
    def is_python(executable: str) -> bool:
        """!
        @brief Recognize Python executables and launchers.
        @param executable Command executable, with or without its full path.
        @return True for this runtime or a standard Python executable name.
        """
        name = Path(executable.replace("\\", "/")).name.lower()
        return executable == sys.executable or bool(
            re.fullmatch(
                r"(?:pythonw?|pypy|py)(?:\d+(?:\.\d+)*)?(?:\.exe)?", name
            )
        )

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
        quiet_success: bool = False,
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
        @param quiet_success True to keep successful command output in verbose
        mode and the log only. Failures remain visible in normal mode.
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
            status = result.returncode
        except OSError as error:
            full = normal = str(error)
            status = 1
        self._command_details(command, tool, options, status, environment)
        self.detail(
            full,
            normal="" if quiet_success and status == 0 else normal,
            literal=literal,
        )
        return status

    def _command_details(
        self,
        command: list[str],
        tool: str,
        options: Sequence[str],
        status: int,
        environment: Mapping[str, str],
    ) -> None:
        """!
        @brief Record which tool ran and the arguments it received.
        @param command Complete subprocess command, including options.
        @param tool Name derived from the executable and module arguments.
        @param options Arguments appended by command and included as evidence.
        @param status Tool exit code, or one if it could not run.
        @param environment Variables used by the tool and its version lookup.
        """
        identity = f"{tool} (version unavailable)"
        if self.is_python(command[0]):
            module, _ = self._module(command[1:])
            packages = tool.split(" / ") if module else [""]
            versions = []
            for package in packages:
                installed = self._tool_version(command, package, environment)
                if package and installed.startswith("Python "):
                    installed += f" ({package})"
                versions.append(installed)
            identity = " / ".join(versions)
        if identity not in self.tools:
            self.detail(f"- Tool: {identity}")
            self.tools.add(identity)
        if options:
            self.detail(f"- Options: {shlex.join(options)}", normal="")
        self.detail(
            f"- Exit status: {status}", normal="" if status == 0 else None
        )

    def _tool_version(
        self, command: list[str], package: str, environment: Mapping[str, str]
    ) -> str:
        """!
        @brief Read a tool's version from the Python that ran it.
        @param command Tool command, including any Python launcher selector.
        @param package Module to look up, or empty for Python itself.
        @param environment Variables passed to that Python process.
        @return Package version, Python version for standard-library tools,
        or an unavailable message when the lookup fails.
        """
        if command[0] == sys.executable:
            if not package or package.split(".")[0] in sys.stdlib_module_names:
                return f"Python {platform.python_version()}"
            try:
                return f"{package} {version(package)}"
            except PackageNotFoundError:
                return f"{package} unavailable"

        module, _ = self._module(command[1:])
        python = command[: command.index("-m")] if module else command[:1]
        probe = (
            "import sys\n"
            "from importlib.metadata import version\n"
            "from platform import python_version\n"
            "name = sys.argv[1]\n"
            "if not name or name.split('.')[0] in sys.stdlib_module_names:\n"
            "    print('Python ' + python_version())\n"
            "else:\n"
            "    print(name + ' ' + version(name))\n"
        )
        try:
            result = subprocess.run(
                [*python, "-I", "-c", probe, package],
                cwd=self.root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return f"{package or 'Python'} unavailable"

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

        self.results[label] = "WARN" if details else "PASS"
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
        @brief Print warnings followed by the final result.
        @return One if any required check failed, otherwise zero. Warnings alone
        do not fail the commit.
        """

        self.release()
        warnings = [
            f"- {label}: {', '.join(details)}"
            for label, details in self.advisories.items()
            if details
        ]
        warnings.extend(
            f"- {label}: NOT RUN"
            for label, status in self.results.items()
            if status == "NOT RUN"
        )
        if warnings:
            for message in warnings:
                self.detail(message)
            self.section("Warnings", "WARN", always=True)
        if self.failures:
            self.detail("Failed sections:", literal=True)
            for label in self.failures:
                self.detail(f"- {label}")
            self.detail("Verbose: git hook run pre-commit -- --verbose")
        self.section("Result", "FAIL" if self.failures else "PASS", always=True)
        return int(bool(self.failures))
