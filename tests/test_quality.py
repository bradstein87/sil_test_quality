"""!
@brief Tests for complexity and coverage requirements.
"""

import json

import pytest

from sil_test_quality import configuration as policy
from sil_test_quality.output import CheckOutput
from sil_test_quality.quality import ComplexityChecks, CoverageChecks
from sil_test_quality.reports.coverage import CoverageReport
from sil_test_quality.source import ProjectSource


class TestCoverageChecks:
    """!
    @brief Check per-file coverage and separate branch warnings.
    """

    def write_coverage(self, tmp_path, document):
        """!
        @brief Write a controlled result for the fake coverage command.
        @param tmp_path Test repo where artifacts/coverage.json is expected.
        @param document Coverage measurement dictionary to save as the fake JSON
        export.
        @return Zero to simulate a successful coverage command.
        """
        (tmp_path / "artifacts/coverage.json").write_text(json.dumps(document))
        return 0

    @pytest.fixture
    def coverage_summary(self, tmp_path, monkeypatch):
        """!
        @brief Provide adjustable statement and branch measurements.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @return Mutable count dictionary the test adjusts before the fake
        coverage export.
        """
        summary = {
            "covered_lines": 100,
            "num_statements": 100,
            "covered_branches": 1,
            "num_branches": 2,
            "percent_covered": 50,
        }
        document = {
            "totals": summary,
            "files": {"src/example.py": {"summary": summary}},
        }
        monkeypatch.setattr(
            CheckOutput,
            "command",
            lambda *args, **kwargs: self.write_coverage(tmp_path, document),
        )
        monkeypatch.setattr(CoverageReport, "render", lambda *args: ("", ""))
        return summary

    @pytest.mark.parametrize("covered", [100, 89])
    def test_coverage_keeps_statements_separate_from_advisory_branches(
        self, tmp_path, coverage_summary, covered
    ):
        """!
        @brief Keep branch warnings separate from the statement verdict.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param coverage_summary Fixture dictionary controlling statement and
        branch counts.
        @param covered Executed statements out of 100, used to set the expected
        verdict.
        """
        coverage_summary["covered_lines"] = covered
        with CheckOutput(tmp_path) as output:
            notes = CoverageChecks(tmp_path, output).run(tmp_path / ".coverage")
            assert output.failures == (["Coverage"] if covered < 90 else [])
            assert output.results["Branch coverage (advisory)"] == "WARN"
            assert f"Statement coverage: {covered:.2f}% overall" in notes
            assert any("Branch coverage: 50.00%" in note for note in notes)

    @pytest.mark.parametrize("status", [0, 1])
    def test_coverage_never_reuses_a_previous_report(
        self, tmp_path, monkeypatch, status
    ):
        """!
        @brief Reject stale coverage when no fresh report is produced.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param status Exit code from the fake command that produces no fresh
        JSON.
        """

        monkeypatch.setattr(
            CheckOutput, "command", lambda *args, **kwargs: status
        )
        with CheckOutput(tmp_path) as output:
            report = tmp_path / "artifacts/coverage.json"
            report.write_text('{"totals": {"percent_covered": 100}}')
            CoverageChecks(tmp_path, output).run(tmp_path / ".coverage")
            assert output.failures
            assert output.results["Branch coverage (advisory)"] == "NOT RUN"
            assert not report.exists()

    def test_shared_coverage_limit_matches_the_report(
        self, tmp_path, monkeypatch, coverage_summary
    ):
        """!
        @brief Apply the shared coverage limit to both verdicts and messages.
        @param tmp_path Temporary repo where the fake measurements are written.
        @param monkeypatch Change the shared coverage limit for this test only.
        @param coverage_summary Controlled statement and branch measurements.
        """
        monkeypatch.setattr(policy, "MIN_FILE_COVERAGE", 95)
        coverage_summary["covered_lines"] = 94
        with CheckOutput(tmp_path) as output:
            CoverageChecks(tmp_path, output).run(tmp_path / ".coverage")
            assert output.results["Coverage"] == "FAIL"
        log = output.path.read_text()
        assert "Statements: >= 95%" in log
        assert "Below 95%: src/example.py (94.00%)" in log


class TestComplexityChecks:
    """!
    @brief Check Lizard limits, length warnings and tool failures.
    """

    @pytest.mark.parametrize("branches, failed", [(19, False), (20, True)])
    def test_lizard_blocks_complexity_above_twenty(
        self, tmp_path, branches, failed
    ):
        """!
        @brief Fail functions above CCN 20 using real Lizard measurements.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param branches Decision count used to generate the measured function.
        @param failed Expected blocking result for that function's CCN.
        """

        (tmp_path / "sample with spaces.py").write_text(
            "def decisions(value):\n"
            + "    if value:\n        value += 1\n" * branches
        )
        with CheckOutput(tmp_path) as output:
            notes = ComplexityChecks(ProjectSource(tmp_path), output).run()
            assert bool(output.failures) == failed
            assert f"Maximum CCN: {branches + 1}" in notes[0]
        log = (tmp_path / "artifacts/precommit.log").read_text()
        assert "NLOC" in log and "CCN" in log
        assert "decisions" in log and "sample with spaces.py" in log

    @pytest.mark.parametrize("lines, warning", [(60, False), (61, True)])
    def test_lizard_length_is_advisory_and_exclusions_apply(
        self, tmp_path, lines, warning
    ):
        """!
        @brief Treat length as advisory and honor source exclusions.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param lines Body size used to generate the sample function.
        @param warning Whether that function should trigger the length advisory.
        """

        (tmp_path / "sample.py").write_text(
            "def long_function():\n" + "    value = 1\n" * (lines - 1)
        )
        (tmp_path / "legacy.py").write_text(
            "def excluded(value):\n"
            + "    if value:\n        value += 1\n" * 30
        )
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools/exclusions.py").write_text(
            "EXCLUDED_FILES = ['legacy.py']\n"
        )
        environment = tmp_path / "custom-venv"
        environment.mkdir()
        (environment / "pyvenv.cfg").touch()
        (environment / "generated.py").write_text("def broken(\n")
        # Git ignore rules must not hide maintained inputs from checks.
        (tmp_path / ".gitignore").write_text("sample.py\n")
        with CheckOutput(tmp_path) as output:
            notes = ComplexityChecks(ProjectSource(tmp_path), output).run()
            assert not output.failures
            assert "Maximum CCN: 1" in notes[0]
            assert output.results["Length"] == ("WARN" if warning else "PASS")
        log = (tmp_path / "artifacts/precommit.log").read_text()
        assert "long_function" in log.split("| Length ")[1]
        assert "excluded@" not in log and "generated.py" not in log

    def test_lizard_tool_failure_is_not_an_advisory(
        self, tmp_path, monkeypatch
    ):
        """!
        @brief Fail Complexity when Lizard cannot produce measurements.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """

        monkeypatch.setattr(CheckOutput, "command", lambda *args, **kwargs: 1)
        with CheckOutput(tmp_path) as output:
            ComplexityChecks(ProjectSource(tmp_path), output).run()
            assert output.failures == ["Complexity"]
            assert output.results["Length"] == ("NOT RUN")

    def test_shared_limits_control_lizard_and_the_report(
        self, tmp_path, monkeypatch
    ):
        """!
        @brief Keep Lizard arguments, verdicts and length tables in agreement.
        @param tmp_path Temporary repo with a function containing branches.
        @param monkeypatch Change both shared limits for this test only.
        """
        monkeypatch.setattr(policy, "MAX_COMPLEXITY", 2)
        monkeypatch.setattr(policy, "FUNCTION_REVIEW_LINES", 4)
        (tmp_path / "sample.py").write_text(
            "def choose(value):\n"
            "    if value == 1:\n        return 1\n"
            "    if value == 2:\n        return 2\n"
            "    return 0\n"
        )
        with CheckOutput(tmp_path) as output:
            ComplexityChecks(ProjectSource(tmp_path), output).run()
            assert output.results["Complexity"] == "FAIL"
            assert output.results["Length"] == "WARN"
        log = output.path.read_text()
        assert "CCN <= 2" in log and "-C2 -L4" in log
        assert "review above 4 physical lines" in log
        assert "choose@" in log.split("| Length ")[1]


class TestPerFileThreshold:
    """!
    @brief Check the 90% per-file coverage boundary.
    """

    def test_ninety_percent_in_every_file_is_sufficient(self, tmp_path):
        """!
        @brief Accept 90% per file without a higher overall requirement.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        for covered, failed in [(90, False), (94, False), (89, True)]:
            summary = {
                "covered_lines": covered,
                "num_statements": 100,
                "covered_branches": 0,
                "num_branches": 10,
            }
            report = {
                "totals": summary,
                "files": {"src/a.py": {"summary": summary}},
            }
            with CheckOutput(tmp_path) as output:
                CoverageChecks(tmp_path, output)._evaluate(report, "Coverage")
                assert bool(output.failures) == failed
                assert output.results["Branch coverage (advisory)"] == "WARN"

    def test_empty_measurement_is_not_a_pass(self, tmp_path):
        """!
        @brief Reject coverage data with no measured source files.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        with CheckOutput(tmp_path) as output, pytest.raises(ValueError):
            CoverageChecks(tmp_path, output)._evaluate(
                {
                    "totals": {"covered_lines": 0, "num_statements": 0},
                    "files": {},
                },
                "Coverage",
            )
