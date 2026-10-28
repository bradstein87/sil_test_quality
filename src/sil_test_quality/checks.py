"""!
@brief Precommit check sequence and overall result.
"""

import json
import sys
from pathlib import Path

from . import configuration as policy
from .docstrings import DoxygenDocstrings
from .output import CheckOutput
from .quality import ComplexityChecks, CoverageChecks
from .report import QualityReport
from .reports.diagnostics import DiagnosticReport
from .reports.settings import SettingsReport
from .reports.tests import TestReport
from .source import ProjectSource


class RepositoryChecks:
    """!
    @brief Run the checks against a selected repo.
    @details Failed checks are recorded while later checks continue. Optional
    repairs happen first. Tests produce the measurements used by the coverage
    check.
    """

    EXCLUDED_DIRECTORIES = ProjectSource.GENERATED

    def __init__(self, root: Path) -> None:
        """!
        @brief Load the repo scope and check settings.
        @param root Repo to check, containing its source, tests and
        configuration.
        """

        self.root = root.resolve()
        self.settings = policy.CheckSettings(self.root)
        self.source = ProjectSource(self.root)
        self.exclusions = self.source.exclusions

    def run(
        self, fix: bool = False, verbose: bool = False, brief: bool = False
    ) -> int:
        """!
        @brief Run the checks and produce the precommit report.
        @details Normal output is the default. The saved log contains full
        evidence in every display mode.
        @param fix True to repair imports and formatting before checking.
        @param verbose True to show complete console evidence.
        @param brief True to show verdicts and the final summary only.
        @return Exit status for Git: zero when checks pass, one when any
        required check fails.
        """

        with CheckOutput(self.root, verbose, brief=brief) as output:
            return self._run(output, fix)

    def ruff_exclusions(self) -> list[str]:
        """!
        @brief Prepare the file exclusions used by Ruff.
        @return Ruff arguments to skip generated content, virtual environments
        and declared legacy files.
        """

        environments = [
            directory.relative_to(self.root).as_posix()
            for directory, names in self.source.directories()
            if "pyvenv.cfg" in names
        ]
        exclusions = environments + sorted(self.EXCLUDED_DIRECTORIES)
        exclusions += [str(self.root / name) for name in self.exclusions]
        return ["--config", f"extend-exclude = {json.dumps(exclusions)}"]

    def repair(self, output: CheckOutput, exclusions: list[str]) -> None:
        """!
        @brief Fix imports and formatting in the checked files.
        @param output Report recorder receiving this check's evidence and
        results.
        @param exclusions Arguments from ruff_exclusions telling Ruff which
        files to skip.
        """

        for label, operation, args in (
            ("Imports", "check", ["--select", "I", "--fix"]),
            ("Format", "format", []),
        ):
            output.start(label)
            status = output.command(
                [sys.executable, "-m", "ruff", operation],
                options=[*args, ".", *exclusions],
            )
            output.result(label, status == 0)

    def _run(self, output: CheckOutput, fix: bool) -> int:
        """!
        @brief Run each check stage and collect the final result.
        @details Old test and coverage artifacts are removed first. The final
        consistency check detects source changes made during the run.
        @param output Report recorder receiving this check's evidence and
        results.
        @param fix Repair choice passed by run. True applies fixes first.
        @return Final exit status from CheckOutput: zero for pass, one for
        failure.
        """
        exclusions = self.ruff_exclusions()
        if fix:
            self.repair(output, exclusions)
        report = QualityReport(self.source)
        report.begin(output)
        # Fresh artifacts only. A failed stage must not inherit an old result.
        for name in (".coverage", "coverage.json", "unit-tests.xml"):
            (self.root / "artifacts" / name).unlink(missing_ok=True)
        self.check_files(output)
        suppressions = self.check_structure(output)
        DoxygenDocstrings().run(self.source, output)
        ComplexityChecks(self.source, output).run()
        self.check_settings(output, exclusions)
        self.check_style(output, exclusions)
        self.check_formatting(output, exclusions)
        self.check_types(output)
        self.check_tests(output)
        output.detail(
            "- Coverage omissions: "
            + (", ".join(self.settings.coverage_omit) or "none")
            + (". Legacy exclusions also apply" if self.exclusions else "")
        )
        CoverageChecks(self.root, output).run(self.root / "artifacts/.coverage")
        report.emit(output, suppressions)
        return output.finish()

    def check_files(self, output: CheckOutput) -> None:
        """!
        @brief Check files against the shared length limit.
        @param output Report recorder receiving this check's evidence and
        results.
        """
        output.start("Files")
        sizes = sorted(
            self.source.sizes(),
            key=lambda row: int(row.rsplit(": ", 1)[1].split()[0]),
            reverse=True,
        )
        output.detail(
            f"- File length: <= {policy.MAX_FILE_LINES} physical lines"
        )
        output.detail(
            "\n".join(sizes), normal="\n".join(sizes[: policy.NORMAL_ROWS])
        )
        output.detail(f"- Files over limit: {len(sizes)}")
        output.result("Files", not sizes)

    def check_structure(self, output: CheckOutput) -> list[str]:
        """!
        @brief Check code structure and collect inline exceptions.
        @param output Report recorder receiving this check's evidence and
        results.
        @return Inline exceptions such as noqa, passed to QualityReport for
        disclosure.
        """
        output.start("Structure")
        problems, suppressions = self.source.inspect()
        output.detail("- Classes: no multiple inheritance")
        output.detail("- Tests: class-based organization")
        output.detail("- Comments: no unfinished-work markers")
        full, normal = DiagnosticReport().render("\n".join(problems))
        output.detail(full, normal=normal)
        output.detail(f"- Violations: {len(problems)}")
        output.result("Structure", not problems)
        return suppressions

    def check_settings(
        self, output: CheckOutput, exclusions: list[str]
    ) -> None:
        """!
        @brief Include Ruff's resolved settings in the report.
        @param output Report recorder receiving the settings and result.
        @param exclusions Arguments used by the lint and formatting commands.
        """
        output.start("Settings")
        status = output.command(
            [sys.executable, "-m", "ruff", "check"],
            options=["--show-settings", ".", *exclusions],
            view=SettingsReport().render,
            literal=True,
        )
        output.result("Settings", status == 0)

    def check_formatting(
        self, output: CheckOutput, exclusions: list[str]
    ) -> bool:
        """!
        @brief Check formatting without changing the files.
        @param output Report recorder receiving this check's evidence and
        results.
        @param exclusions Arguments from ruff_exclusions telling Ruff which
        files to skip.
        @return True when Ruff accepts the formatting, or false for findings or
        tool failure.
        """
        output.start("Formatting")
        output.detail("- Whitespace and layout: repository formatting rules")
        status = output.command(
            [sys.executable, "-m", "ruff", "format"],
            options=["--check", ".", *exclusions],
        )
        if status:
            output.detail("- Fix: git hook run pre-commit -- --fix")
        output.result("Formatting", status == 0)
        return status == 0

    def check_style(self, output: CheckOutput, exclusions: list[str]) -> bool:
        """!
        @brief Check source style with the repo's Ruff rules.
        @param output Report recorder receiving this check's evidence and
        results.
        @param exclusions Arguments from ruff_exclusions telling Ruff which
        files to skip.
        @return True if Ruff passes, or false for lint findings or tool failure.
        """

        label = "Lint"
        output.start(label)
        output.detail(
            "- Naming, imports and source style: repository lint rules"
        )
        status = output.command(
            [sys.executable, "-m", "ruff", "check"],
            options=["--output-format=concise", ".", *exclusions],
        )
        output.result(label, status == 0)
        return status == 0

    def check_types(self, output: CheckOutput) -> None:
        """!
        @brief Check source types with mypy.
        @param output Report recorder receiving this check's evidence and
        results.
        """

        output.start("Types")
        files = [
            str(path.relative_to(self.root))
            for path in self.source.files()
            if path.suffix == ".py" and path.is_relative_to(self.root / "src")
        ]
        output.detail("- Function interfaces: parameter and return type checks")
        output.detail(f"- Source files: {len(files)}")
        if not files:
            output.detail("No source files were found for type checking")
            output.result("Types", False)
            return
        # An argument file avoids Windows' command-line length limit.
        arguments = self.root / "artifacts/mypy-files.txt"
        arguments.write_text("\n".join(files) + "\n", encoding="utf-8")
        status = output.command(
            [sys.executable, "-m", "mypy"],
            options=["--follow-imports=silent", "@" + str(arguments)],
        )
        output.result("Types", status == 0)

    def check_tests(self, output: CheckOutput) -> None:
        """!
        @brief Run pytest and collect source coverage.
        @details Writes fresh coverage data and JUnit XML under artifacts. This
        stage checks test results. CoverageChecks applies the per-file coverage
        requirement afterward.
        @param output Report recorder receiving this check's evidence and
        results.
        """

        output.start("Tests")
        omit = self.settings.coverage_omit + self.exclusions
        output.detail(f"- Suite: {self.settings.test_label}")
        output.detail("- Software tests: no test failures or execution errors")
        options = [
            "--branch",
            f"--data-file={self.root / 'artifacts/.coverage'}",
            "--source=src",
        ]
        if omit:
            options.append(f"--omit={','.join(omit)}")
        options += [
            "-m",
            "pytest",
            "tests",
            "-v",
            "-ra",
            "--junitxml=artifacts/unit-tests.xml",
        ]
        status = output.command(
            [sys.executable, "-m", "coverage", "run"],
            options=options,
            view=TestReport().render,
            literal=True,
        )
        output.result("Tests", status == 0)
