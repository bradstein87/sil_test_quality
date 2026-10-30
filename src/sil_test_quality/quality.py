"""!
@brief Complexity and coverage requirements applied to tool measurements.
"""

import json
import sys
from pathlib import Path
from typing import Any

import lizard
from coverage.exceptions import CoverageException

from sil_test_quality import configuration as policy
from sil_test_quality.output import CheckOutput
from sil_test_quality.reports.coverage import CoverageReport
from sil_test_quality.reports.tables import LizardReport
from sil_test_quality.source import ProjectSource


class ComplexityChecks:
    """!
    @brief Check complexity limits and report long functions.
    @details Complexity above the shared limit blocks the commit. Long functions
    produce a review warning.
    """

    def __init__(self, source: ProjectSource, output: CheckOutput) -> None:
        """!
        @brief Set the source scope and report recorder.
        @param source ProjectSource providing the repo files and exclusions to
        check.
        @param output Report recorder receiving this check's evidence and
        results.
        """

        self.source, self.output = source, output

    def run(self) -> list[str]:
        """!
        @brief Measure functions and report complexity and length.
        @return Measurement summary strings, or an unavailable notice if Lizard
        fails. Verdicts are recorded through output.
        """

        self.output.start("Complexity")

        files = [path for path in self.source.files() if path.suffix == ".py"]
        label = "Complexity"
        length_label = "Length"
        report = LizardReport()
        status = self._invoke(files, report)
        if status:
            self.output.result(label, False)
            self.output.results[length_label] = "NOT RUN"
            return ["Lizard measurements unavailable"]
        # The native table includes both limits. Only CCN blocks a commit.
        functions = [
            function
            for path in files
            for function in lizard.analyze_file(str(path)).function_list
        ]
        maximum = max(
            (function.cyclomatic_complexity for function in functions),
            default=0,
        )
        long_functions = sum(
            function.length > policy.FUNCTION_REVIEW_LINES
            for function in functions
        )
        notes = [f"Maximum CCN: {maximum}"]
        self.output.detail(notes[0])
        self.output.result(label, maximum <= policy.MAX_COMPLEXITY)
        self._report_length(report, long_functions)
        return notes

    def _invoke(self, files: list[Path], report: LizardReport) -> int:
        """!
        @brief Run Lizard against the selected Python files.
        @param files Paths from ProjectSource written to Lizard's input file
        list.
        @param report LizardReport that formats captured tables and saves rows
        for lengths.
        @return Lizard exit code used by run to check whether measurements are
        available.
        """
        arguments = self.source.root / "artifacts/lizard-files.txt"
        arguments.write_text(
            "\n".join(str(path.relative_to(self.source.root)) for path in files)
            + "\n",
            encoding="utf-8",
        )
        self.output.detail(
            f"- Complexity: CCN <= {policy.MAX_COMPLEXITY} per function"
        )
        return self.output.command(
            [sys.executable, "-m", "lizard"],
            options=[
                "-l",
                "python",
                f"-C{policy.MAX_COMPLEXITY}",
                f"-L{policy.FUNCTION_REVIEW_LINES}",
                "-i",
                "-1",
                "--no-gitignore",
                "-f",
                str(arguments),
            ],
            view=report.render,
            literal=True,
        )

    def _report_length(self, report: LizardReport, long_functions: int) -> None:
        """!
        @brief Report function lengths and record review warnings.
        @param report LizardReport populated by _invoke with this run's function
        rows.
        @param long_functions Number of functions above the review limit.
        """
        length_label = "Length"
        self.output.start(length_label)
        self.output.warning(
            length_label,
            [
                f"{long_functions} functions above "
                f"{policy.FUNCTION_REVIEW_LINES} lines."
            ]
            if long_functions
            else [],
        )
        self.output.detail(
            f"- Function length: review above {policy.FUNCTION_REVIEW_LINES} "
            "physical lines (advisory)"
        )
        full, normal = report.lengths()
        self.output.detail(full, normal=normal, literal=True)
        self.output.section(length_label, self.output.results[length_label])


class CoverageChecks:
    """!
    @brief Check per-file coverage and report branch coverage.
    @details Each source file must meet the shared statement coverage minimum.
    Overall coverage is informational. Missed branches produce a warning.
    """

    def __init__(self, root: Path, output: CheckOutput) -> None:
        """!
        @brief Set the repo location and coverage report recorder.
        @param root Repo containing source files and measurements from its test
        run.
        @param output Report recorder receiving this check's evidence and
        results.
        """

        self.root, self.output = root, output

    @staticmethod
    def percent(summary: dict[str, Any], covered: str, total: str) -> float:
        """!
        @brief Calculate a coverage percentage from measured counts.
        @param summary Count dictionary from coverage.json for a file or the
        whole run.
        @param covered Key for the executed count, such as covered_lines.
        @param total Key for the matching total, such as num_statements.
        @return Coverage percentage, or 100 when the total is zero.
        """

        return (
            100.0 * summary[covered] / summary[total]
            if summary[total]
            else 100.0
        )

    def run(self, data: Path) -> list[str]:
        """!
        @brief Read test coverage measurements and check the files.
        @details Deletes the previous JSON export first. Missing or invalid
        fresh data fails the check rather than reusing earlier results.
        @param data Path to the coverage database produced during tests,
        exported to JSON here.
        @return Coverage summary strings, or an unavailable notice on failure.
        The verdict is recorded through output.
        """
        label = "Coverage"
        self.output.start(label)
        self.output.detail(
            f"- Statements: >= {policy.MIN_FILE_COVERAGE}% in every source "
            "file, no overall threshold"
        )
        self.output.detail("- Branches: measured for advisory warnings")
        path = self.root / "artifacts/coverage.json"
        path.unlink(missing_ok=True)
        status = self.output.command(
            [sys.executable, "-m", "coverage", "json"],
            options=[f"--data-file={data}", "--fail-under=0", "-o", str(path)],
            quiet_success=True,
        )
        try:
            if status:
                raise ValueError("Coverage could not produce a fresh report")
            report = json.loads(path.read_text(encoding="utf-8"))
            full, normal = CoverageReport(self.root).render(report)
            self.output.detail(full, normal=normal, literal=True)
            return self._evaluate(report, label)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            ZeroDivisionError,
            CoverageException,
        ) as error:
            self.output.detail(f"Could not read the coverage report: {error}")
            self.output.result(label, False)
            self.output.results["Branch coverage (advisory)"] = "NOT RUN"
            return ["Coverage measurements unavailable"]

    def _evaluate(self, report: dict[str, Any], label: str) -> list[str]:
        """!
        @brief Check each source file against the coverage minimum.
        @details A high overall percentage cannot compensate for a file below
        the minimum. Branch counts are evaluated separately as an advisory.
        @param report Dictionary from the coverage tool with per-file and
        overall counts.
        @param label Section name used to record the coverage verdict.
        @return Overall, lowest-file and branch coverage summaries written to
        the report.
        @throws ValueError The measurement contains no source files to evaluate.
        """
        overall = self.percent(
            report["totals"], "covered_lines", "num_statements"
        )
        notes = [f"Statement coverage: {overall:.2f}% overall"]
        failed = False
        violations = []
        percentages = []
        for name, record in report["files"].items():
            percent = self.percent(
                record["summary"], "covered_lines", "num_statements"
            )
            percentages.append(percent)
            if percent < policy.MIN_FILE_COVERAGE:
                violations.append(
                    (
                        percent,
                        f"Below {policy.MIN_FILE_COVERAGE}%: "
                        f"{name} ({percent:.2f}%)",
                    )
                )
                failed = True
        violations.sort()
        self.output.detail(
            "\n".join(row for _, row in violations),
            normal="\n".join(
                row for _, row in violations[: policy.NORMAL_ROWS]
            ),
        )
        if not percentages:
            raise ValueError("No source files in coverage report")
        notes.append(
            f"Statement coverage: {min(percentages):.2f}% lowest file "
            f"across {len(percentages)} measured files"
        )
        notes.append(self._branches(report["totals"]))
        # The table already includes the overall statement percentage.
        for note in notes[1:]:
            self.output.detail(note)
        self.output.result(label, not failed)
        return notes

    def _branches(self, summary: dict[str, Any]) -> str:
        """!
        @brief Report branch coverage as an advisory.
        @param summary Overall counts from coverage.json, including executed and
        total branches.
        @return Branch percentage and counts for the coverage report. Missed
        branches also record a warning.
        """
        branches = summary["num_branches"]
        covered = summary["covered_branches"]
        percent = self.percent(summary, "covered_branches", "num_branches")
        counts = (
            f"{percent:.2f}% ({covered}/{branches}), "
            f"{branches - covered} code branches not exercised"
        )
        self.output.warning(
            "Branch coverage (advisory)", [counts] if covered < branches else []
        )
        return f"Branch coverage: {counts}"
