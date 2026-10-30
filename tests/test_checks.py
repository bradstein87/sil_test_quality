"""!
@brief Tests for the complete precommit check sequence.
"""

import re
import shutil
from pathlib import Path

import pytest

from sil_test_quality import configuration as policy
from sil_test_quality.checks import RepositoryChecks
from sil_test_quality.output import CheckOutput


class TestRepositoryChecks:
    """!
    @brief Check exclusions, repairs and combined check results.
    """

    def test_checks_exclude_virtual_environments_regardless_of_name(
        self, checked_project
    ):
        """!
        @brief Skip virtual environments regardless of directory name.
        @param checked_project Fixture repo with passing source and tests to
        build this scenario on.
        """

        root = checked_project
        for name in ("custom environment", "nested/another-python"):
            environment = root / name
            environment.mkdir(parents=True)
            (environment / "pyvenv.cfg").touch()
            (environment / "installed.py").write_text(
                "not valid Python\n" * 501
            )

        assert RepositoryChecks(root).run() == 0

    def test_temporary_exclusions_cover_source_checks_and_can_be_removed(
        self, project_with_legacy_file, capfd
    ):
        """!
        @brief Resume checking legacy files when exclusions are removed.
        @param project_with_legacy_file Fixture repo with invalid legacy files
        and explicit exclusions.
        @param capfd Pytest capture including child-process output for report
        assertions.
        """

        root = project_with_legacy_file
        assert RepositoryChecks(root).run(verbose=True) == 0
        output = capfd.readouterr().out
        assert "Legacy excluded:" in output
        assert "legacy/old_tool.py" in output
        assert "1 passed" in output

        (root / "tools/exclusions.py").write_text("EXCLUDED_FILES = ()\n")
        assert RepositoryChecks(root).run(verbose=True) == 1
        output = capfd.readouterr().out
        assert "501 lines" in output
        assert "1 passed" in output

    def test_temporary_exclusions_leave_other_files_and_tests_checked(
        self, project_with_legacy_file, capfd
    ):
        """!
        @brief Keep checking files outside the legacy exclusion list.
        @param project_with_legacy_file Fixture repo with invalid legacy files
        and explicit exclusions.
        @param capfd Pytest capture including child-process output for report
        assertions.
        """

        root = project_with_legacy_file
        # An exclusion applies to one path, not every file with that name.
        (root / "other").mkdir()
        other_file = root / "other/root_tool.py"
        other_file.write_text("not valid Python\n" * 501)
        assert RepositoryChecks(root).run(verbose=True) == 1
        output = capfd.readouterr().out
        assert "501 lines" in output
        assert "other/root_tool.py" in output.replace("\\", "/")

        other_file.write_text("value = 1\n")
        (root / "tests/test_example.py").write_text(
            "class TestExample:\n"
            "    def test_answer(self):\n        assert False\n"
        )
        assert RepositoryChecks(root).run(verbose=True) == 1
        assert "1 failed" in capfd.readouterr().out

    def test_style_repair_preserves_excluded_files(
        self, unformatted_project, capfd
    ):
        """!
        @brief Repair style without changing excluded legacy files.
        @param unformatted_project Fixture repo with fixable style errors beside
        excluded legacy files.
        @param capfd Pytest capture including child-process output for report
        assertions.
        """

        root = unformatted_project
        legacy_file = root / "src/legacy/old_tool.py"
        legacy_contents = legacy_file.read_bytes()
        test_file = root / "tests/test_example.py"
        original = test_file.read_bytes()
        checks = RepositoryChecks(root)
        assert checks.run(verbose=True) == 1
        assert test_file.read_bytes() == original
        output = capfd.readouterr().out
        assert "I001" in output
        assert "E501" in output
        assert "git hook run pre-commit -- --fix" in output

        assert checks.run(fix=True, verbose=True) == 0
        assert test_file.read_bytes() != original
        assert (
            max(len(line) for line in test_file.read_text().splitlines()) <= 80
        )
        assert legacy_file.read_bytes() == legacy_contents
        output = capfd.readouterr().out
        assert "1 passed" in output
        assert "git hook run pre-commit -- --fix" not in output

        # Same-size edits within one second can reuse cached bytecode. Use a new
        # file for the failing test.
        (root / "tests/test_failure.py").write_text(
            "class TestFailure:\n    def test_failure(self):\n"
            '        assert False, "Intentional test failure"\n'
        )
        assert checks.run(fix=True, verbose=True) == 1
        output = capfd.readouterr().out
        assert "1 failed" in output
        assert "Intentional test failure" in output
        assert "Some style issues need manual edits" not in output

    def test_coverage_gate_counts_unimported_source_but_not_product_cases(
        self, checked_project, capfd
    ):
        """!
        @brief Measure unimported source while omitting product cases.
        @param checked_project Fixture repo with passing source and tests to
        build this scenario on.
        @param capfd Pytest capture including child-process output for report
        assertions.
        """

        root = checked_project
        package = root / "src/vv_test_verification"
        cases = package / "cases"
        cases.mkdir(parents=True)
        (package / "__init__.py").touch()
        (cases / "__init__.py").touch()
        (cases / "test_product.py").write_text(
            '"""! @brief Example product cases."""\n\n\n'
            "def test_product() -> None:\n"
            '    """! @brief Deliberately fail the product case."""\n'
            '    raise AssertionError("Product failed")\n'
        )
        assert RepositoryChecks(root).run(verbose=True) == 0
        assert "100.00%" in capfd.readouterr().out

        (root / "src/unused.py").write_text("def unused():\n    return 42\n")
        assert RepositoryChecks(root).run(verbose=True) == 1
        output = capfd.readouterr().out
        assert "1 passed" in output
        assert "Below 90%" in output
        assert "unused.py" in output

    def test_quiet_summary_names_failed_stages_and_keeps_details_in_the_log(
        self, checked_project, capfd
    ):
        """!
        @brief Keep full failure evidence when console output is shortened.
        @param checked_project Fixture repo with passing source and tests to
        build this scenario on.
        @param capfd Pytest capture including child-process output for report
        assertions.
        """

        checks = RepositoryChecks(checked_project)
        assert checks.run() == 0
        output = capfd.readouterr().out
        assert re.search(r"\| Result +PASS \|", output)
        assert "Failed sections:" not in output
        assert "Verbose: git hook run pre-commit" not in output
        assert re.search(r"\| Tests +PASS \|", output)
        assert "Suite:" not in output and "Wrote JSON" not in output
        assert "Test selection: tests" in output
        assert "::test_answer PASSED" in output
        assert "1 passed" in output and "collected 1 item" in output
        log = checked_project / "artifacts/precommit.log"
        assert "1 passed" in log.read_text()
        assert "Wrote JSON report" in log.read_text()

        (checked_project / "notes.txt").write_text("line\n" * 501)
        (checked_project / "tests/test_example.py").write_text(
            '"""! @brief Check the example."""\n\n'
            "from src.example import ANSWER\n\n\nclass TestExample:\n"
            '    """! @brief Example checks."""\n\n'
            "    def test_answer(self):\n"
            '        """! @brief Reject the fixed answer."""\n'
            "        assert ANSWER != 42, "
            '"wrong answer"\n'
        )
        assert checks.run() == 1
        output = capfd.readouterr().out
        assert re.search(r"\| Result +FAIL \|", output)
        assert re.search(r"\| Files +FAIL \|", output)
        assert re.search(r"\| Tests +FAIL \|", output)
        assert re.search(r"\| Coverage +PASS \|", output)
        assert "test session starts" not in output
        assert "wrong answer" in log.read_text()
        assert "notes.txt: 501 lines" in log.read_text()
        assert "1 passed" not in log.read_text()

    def test_file_coverage_below_90_fails_despite_overall_above_95(
        self, partially_covered_project, capfd
    ):
        """!
        @brief Fail low file coverage despite a high overall percentage.
        @param partially_covered_project Fixture repo with high overall coverage
        but one file below 90%.
        @param capfd Pytest capture including child-process output for report
        assertions.
        """

        root = partially_covered_project
        test = root / "tests/test_example.py"
        checks = RepositoryChecks(root)
        assert checks.run(verbose=True) == 1
        output = capfd.readouterr().out
        assert "96.00%" in output
        assert "Below 90%: src/choice.py (75.00%)" in output.replace("\\", "/")
        assert re.search(r"\| Coverage +FAIL \|", output)

        with test.open("a") as stream:
            stream.write('        assert choose(False) == "no"\n')
        assert checks.run() == 0


class TestReportedSettings:
    """!
    @brief Check that report settings match the configuration tools apply.
    """

    def test_ruff_reports_shared_and_consumer_settings(self, checked_project):
        """!
        @brief Report effective rules from the actual generated configuration.
        @param checked_project Repo with a narrower width and an added rule.
        """
        manifest = checked_project / "pyproject.toml"
        with manifest.open("a") as stream:
            stream.write(
                "\n[tool.ruff]\nline-length = 72\n"
                '[tool.ruff.lint]\nextend-select = ["T201"]\n'
            )
        with CheckOutput(checked_project) as output:
            assert RepositoryChecks(checked_project).check_settings(output, [])
        log = output.path.read_text()
        assert "linter.line_length = 72" in log
        assert "formatter.line_width = 72" in log
        assert "PLC0415 (import-outside-top-level)" in log
        assert "T201 (print)" in log
        assert "Effective mypy settings" in log
        assert "Consumer additions" in log

    def test_conflicting_config_stops_before_repairs(self, checked_project):
        """!
        @brief Reject weakened settings before tools can edit source files.
        @param checked_project Repo containing a conflicting Ruff setting.
        """
        manifest = checked_project / "pyproject.toml"
        with manifest.open("a") as stream:
            stream.write('\n[tool.ruff.lint]\nignore = ["PLC0415"]\n')
        path = checked_project / "src/example.py"
        original = path.read_text()
        assert RepositoryChecks(checked_project).run(fix=True) == 1
        assert path.read_text() == original
        log = (checked_project / "artifacts/precommit.log").read_text()
        assert "tool.ruff.lint.ignore" in log

    def test_invalid_rule_fails_settings(self, checked_project):
        """!
        @brief Let Ruff reject unknown rule names before checks run.
        @param checked_project Repo containing a nonexistent extra lint rule.
        """
        manifest = checked_project / "pyproject.toml"
        with manifest.open("a") as stream:
            stream.write('\n[tool.ruff.lint]\nextend-select = ["BOGUS"]\n')
        with CheckOutput(checked_project) as output:
            assert not RepositoryChecks(checked_project).check_settings(
                output, []
            )
        assert output.results["Settings"] == "FAIL"

    def test_missing_rule_metadata_fails_settings(
        self, checked_project, monkeypatch
    ):
        """!
        @brief Reject a settings report when Ruff cannot describe its rules.
        @param checked_project Sample repo used to run the settings check.
        @param monkeypatch Replace tool output with an incomplete catalog.
        """

        def tool_output(command, *, view, **kwargs):
            """!
            @brief Return valid settings followed by missing rule metadata.
            @param command Tool command identifying settings or metadata.
            @param view Report renderer to receive the simulated output.
            @param kwargs Other command options, unused by this replacement.
            @return Zero to isolate failure in the metadata itself.
            """
            if "check" in command:
                view("linter.rules.enabled = [rule (E401)]")
            else:
                view("[]")
            return 0

        with CheckOutput(checked_project) as output:
            monkeypatch.setattr(output, "command", tool_output)
            RepositoryChecks(checked_project).check_settings(output, [])
            assert output.results["Settings"] == "FAIL"

    def test_file_limit_matches_the_report(self, checked_project, monkeypatch):
        """!
        @brief Use the same file limit for findings and report descriptions.
        @param checked_project Sample repo containing a file above the limit.
        @param monkeypatch Change the shared limit for this test only.
        """
        monkeypatch.setattr(policy, "MAX_FILE_LINES", 8)
        (checked_project / "notes.txt").write_text("line\n" * 9)
        with CheckOutput(checked_project) as output:
            RepositoryChecks(checked_project).check_files(output)
            assert output.results["Files"] == "FAIL"
        log = output.path.read_text()
        assert "File length: <= 8 physical lines" in log
        assert "notes.txt: 9 lines (limit is 8)" in log


class TestWidthReport:
    """!
    @brief Check blocking width findings in every report mode.
    """

    @pytest.mark.parametrize("mode", ["normal", "brief", "verbose"])
    def test_width_report_modes(self, checked_project, capsys, mode):
        """!
        @brief Keep every finding in the log while limiting normal output.
        @param checked_project Temporary repo containing valid checker settings.
        @param capsys Capture console output for this report mode.
        @param mode Brief, normal or verbose console output to verify.
        """
        (checked_project / "sample.py").write_text(
            "\n".join("x" * width for width in [81, 82, 83, 84])
        )
        with CheckOutput(
            checked_project, verbose=mode == "verbose", brief=mode == "brief"
        ) as output:
            RepositoryChecks(checked_project).check_width(output)
            assert output.finish() == 1
        console = capsys.readouterr().out
        log = output.path.read_text()
        assert re.search(r"\| Width +FAIL \|", console)
        assert "Measured: 3 Python files, widest 84 columns" in log
        for number in range(1, 5):
            finding = f"sample.py:{number}: {80 + number} columns"
            assert finding in log
            visible = mode == "verbose" or (mode == "normal" and number > 1)
            assert (finding in console) == visible
        assert ("..." in console) == (mode == "normal")

    def test_only_width_failure_blocks_the_run(self, checked_project, capfd):
        """!
        @brief Block an overlong line even when every other check passes.
        @param checked_project Temporary repo with otherwise passing checks.
        @param capfd Capture tool output and the final failure summary.
        """
        path = checked_project / "src/example.py"
        path.write_text(
            path.read_text()
            + "\n"
            + "# https://example.com/".ljust(81, "x")
            + "\n"
        )
        manifest = checked_project / "pyproject.toml"
        manifest.write_text(
            manifest.read_text() + "\n[tool.ruff]\nline-length = 80\n"
            '[tool.ruff.lint]\nextend-select = ["E501"]\n'
        )
        assert RepositoryChecks(checked_project).run() == 1
        console = capfd.readouterr().out
        log = (checked_project / "artifacts/precommit.log").read_text()
        assert re.search(r"\| Width +FAIL \|", console)
        assert re.search(r"\| Lint +PASS \|", console)
        assert re.search(r"\| Formatting +PASS \|", console)
        assert len(re.findall(r"\| \w+ +FAIL \|", console)) == 2
        assert "src/example.py:5: 81 columns (limit is 80)" in log


class TestCheckFailures:
    """!
    @brief Check that tool and source failures block the commit.
    """

    def test_consistency_still_detects_changes_during_tests(
        self, checked_project, monkeypatch, capfd
    ):
        """!
        @brief Keep source-change detection despite reordered report blocks.
        @param checked_project Sample repo with passing source and tests.
        @param monkeypatch Add a source edit after test execution.
        @param capfd Capture the completed report for ordering checks.
        """
        checks = RepositoryChecks(checked_project)
        check_tests = checks.check_tests

        def run_and_edit(output):
            """!
            @brief Change a checked file after collecting test measurements.
            @param output Recorder used by the real test stage.
            """
            check_tests(output)
            (checked_project / "changed.py").write_text("VALUE = 1\n")

        monkeypatch.setattr(checks, "check_tests", run_and_edit)
        assert checks.run() == 1
        console = capfd.readouterr().out
        log = (checked_project / "artifacts/precommit.log").read_text()
        for text in (console, log):
            assert re.search(r"\| Consistency +FAIL \|", text)
            labels = re.findall(r"^\| (\w+) +(?:PASS|FAIL) \|", text, re.M)
            assert labels[-5:] == [
                "Types",
                "Consistency",
                "Coverage",
                "Tests",
                "Result",
            ]
            assert labels[labels.index("Length") + 1] == "Width"
            assert "Warnings" not in text

    def test_failed_lint_tool_blocks_the_check(
        self, checked_project, monkeypatch
    ):
        """!
        @brief Fail the check when the linter fails.
        @param checked_project Sample repo with explicit checker configuration.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """

        monkeypatch.setattr(CheckOutput, "command", lambda *args, **kwargs: 2)
        with CheckOutput(checked_project) as output:
            assert not RepositoryChecks(checked_project).check_style(output, [])
            assert output.failures == ["Lint"]

    def test_new_lint_rules_and_type_errors_block_checks(self, tmp_path):
        """!
        @brief Report violations of the lint and type rules.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """

        root = Path(__file__).resolve().parents[1]
        shutil.copyfile(root / "pyproject.toml", tmp_path / "pyproject.toml")
        source = tmp_path / "src"
        source.mkdir()
        (source / "example.py").write_text(
            '"""An intentionally invalid fixture."""\n'
            "from starlette.requests import Request\n\n"
            "class bad_name:\n    pass\n\n"
            "def convert(value: str) -> int:\n    return value\n\n"
            "def append(value: list = []) -> None:\n    value.append(1)\n"
        )
        with CheckOutput(tmp_path) as output:
            assert not RepositoryChecks(tmp_path).check_style(output, [])
            assert output.results["Lint"] == "FAIL"
            RepositoryChecks(tmp_path).check_types(output)
            assert output.results["Types"] == "FAIL"
        log = (tmp_path / "artifacts/precommit.log").read_text()
        for diagnostic in ("TID251", "N801", "B006", "return-value"):
            assert diagnostic in log

    def test_invalid_python_does_not_report_syntax_checks_as_passed(
        self, checked_project
    ):
        """!
        @brief Fail lint when Python source cannot be parsed.
        @param checked_project Sample repo with explicit checker configuration.
        """

        (checked_project / "broken.py").write_text("def broken(\n")
        with CheckOutput(checked_project) as output:
            assert not RepositoryChecks(checked_project).check_style(output, [])
            assert output.results["Lint"] == "FAIL"
