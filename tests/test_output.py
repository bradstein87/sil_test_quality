"""!
@brief Tests for report recording, display modes and live headers.
"""

import io
import os
import platform
import re
import subprocess
import sys
import venv
from importlib.metadata import version
from pathlib import Path

import pytest

from sil_test_quality.output import CheckOutput


class TestCheckOutput:
    """!
    @brief Check evidence retention and report output behavior.
    """

    def terminal_output(self, monkeypatch):
        """!
        @brief Capture writes to a simulated full-width terminal.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @return In-memory stdout stream used to inspect header frames and report
        blocks.
        """
        stream = io.StringIO()
        monkeypatch.setattr(stream, "isatty", lambda: True)
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr(
            "sil_test_quality.activity.get_terminal_size",
            lambda _: os.terminal_size((120, 24)),
        )
        return stream

    @pytest.mark.parametrize("mode", ["brief", "normal", "verbose"])
    @pytest.mark.parametrize("outcome", ["PASS", "FAIL", "ERROR"])
    def test_live_header_precedes_work_and_finishes_without_duplicate_rows(
        self, tmp_path, monkeypatch, mode, outcome
    ):
        """!
        @brief Finish the live header once without saving animation frames.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param mode Report mode under test: brief, normal or verbose.
        @param outcome Expected PASS, FAIL or ERROR header for the simulated
        check.
        """
        terminal_output = self.terminal_output(monkeypatch)
        output = CheckOutput(
            tmp_path, verbose=mode == "verbose", brief=mode == "brief"
        )
        try:
            with output:
                output.start("Tests")
                assert re.search(
                    r"\| Tests +\.{1,3} \|$", terminal_output.getvalue()
                )
                assert output.path.read_text() == ""
                if outcome == "ERROR":
                    raise RuntimeError("Interrupted check")
                status = output.command(
                    [sys.executable, "-c", "print('test evidence')"]
                )
                assert status == 0
                output.result("Tests", outcome == "PASS")
        except RuntimeError:
            assert outcome == "ERROR"
        assert output.activity.thread is None
        assert output.activity.label == ""
        visible = "\n".join(
            line.rsplit("\r", 1)[-1]
            for line in terminal_output.getvalue().split("\n")
        )
        assert visible.count("| Tests ") == 1
        assert re.search(rf"\| Tests +{outcome} \|", visible)
        assert all(len(row) == 120 for row in visible.splitlines())
        saved = output.path.read_text()
        assert "\r" not in saved
        assert re.search(rf"\| Tests +{outcome} \|", saved)
        if mode != "brief" or outcome == "ERROR":
            assert visible == saved
        else:
            assert "test evidence" not in visible
            assert "test evidence" in saved

    @pytest.mark.parametrize("verbose", [False, True])
    def test_stage_results_are_visible_and_flushed_immediately(
        self, tmp_path, capsys, verbose
    ):
        """!
        @brief Publish each check result before the final summary.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        @param verbose Full-output flag selected for this test scenario.
        """

        with CheckOutput(tmp_path, verbose, brief=not verbose) as output:
            output.detail("All checks passed!")
            output.result("Lint", True)
            output.warning("Lengths", [])
            output.warning("Branches", ["One branch was not exercised"])
            output.result("Tests", False)
            output.result("Coverage", False)
            expected = {
                "Lint": "PASS",
                "Lengths": "PASS",
                "Branches": "WARNING",
                "Tests": "FAIL",
                "Coverage": "FAIL",
            }
            assert output.results == expected
            assert output.failures == ["Tests", "Coverage"]
            console = capsys.readouterr().out
            log = output.path.read_text()
            for label, status in (("Lint", "PASS"), ("Tests", "FAIL")):
                assert re.search(rf"\| {label} +{status} \|", console)
                assert re.search(rf"\| {label} +{status} \|", log)
            assert ("All checks passed!" in console) == verbose
            assert "All checks passed!" in log
            assert "One branch" not in console
            output.finish()

    @pytest.mark.parametrize("verbose", [False, True])
    def test_final_summary_lists_failures_and_advisories(
        self, tmp_path, capsys, verbose
    ):
        """!
        @brief Show failures and warnings in every report mode.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        @param verbose Full-output flag selected for this test scenario.
        """
        with CheckOutput(tmp_path, verbose, brief=not verbose) as output:
            output.result("Tests", False)
            output.result("Coverage", False)
            output.warning("Branches", ["One branch was not exercised"])
            capsys.readouterr()
            assert output.finish() == 1
            ending = capsys.readouterr().out
            assert "One branch was not exercised" in ending
            result_block = ending.split("Warnings")[0]
            assert re.search(r"\| Result +FAIL \|", result_block)
            assert "Failed sections:" in result_block
            assert "- Tests" in result_block and "- Coverage" in result_block
            assert (
                "Verbose: git hook run pre-commit -- --verbose" in result_block
            )
            assert re.search(r"\| Warnings +WARNING \|", ending)
            assert "One branch was not exercised" in ending.splitlines()[-2]
            assert all(len(line) == 120 for line in ending.splitlines())

    @pytest.mark.parametrize("verbose", [False, True])
    def test_tool_output_is_complete_and_exit_status_is_preserved(
        self, tmp_path, capsys, verbose
    ):
        """!
        @brief Keep complete tool output and its exit status.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        @param verbose Full-output flag selected for this test scenario.
        """
        command = [
            sys.executable,
            "-c",
            "import sys; "
            "[print(f'row-{index:04}') for index in range(240)]; "
            "print('tool error', file=sys.stderr); sys.exit(3)",
        ]
        with CheckOutput(tmp_path, verbose, brief=not verbose) as output:
            status = output.command(command, options=("example=1",))
            output.result("Fixture tool", status == 0)
            assert status == 3
            assert output.finish() == 1
        console = capsys.readouterr().out
        log = output.path.read_text()
        for number in range(240):
            assert f"row-{number:04}" in log
            assert (f"row-{number:04}" in console) == verbose
        assert "tool error" in log
        assert "- Options: example=1" in log
        assert "- Command" not in log
        assert "- Exit status: 3" in log
        assert "Remaining files" not in log
        assert all(len(line) == 120 for line in log.splitlines())

    def test_failed_start_and_interrupted_check_retain_diagnostics(
        self, tmp_path, capsys
    ):
        """!
        @brief Keep evidence when a tool or check cannot finish.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        """
        with pytest.raises(RuntimeError), CheckOutput(tmp_path) as output:
            status = output.command([str(tmp_path / "absent")])
            assert status == 1
            output.result("Missing tool", False)
            output.detail("Failure while evaluating collected data")
            raise RuntimeError("Unexpected failure")
        console = capsys.readouterr().out
        assert "Incomplete" in console
        assert "Failure while evaluating collected data" in console
        assert "- Exit status: 1" in output.path.read_text()

    def test_unavailable_advisory_is_visible_at_the_end(self, tmp_path, capsys):
        """!
        @brief Report advisory measurements that could not run.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        """
        with CheckOutput(tmp_path) as output:
            output.result("Coverage", False)
            output.results["Branch coverage"] = "NOT RUN"
            assert output.finish() == 1
        console = capsys.readouterr().out
        assert "- Branch coverage: NOT RUN" in console
        assert "- None" not in console

    def test_findings_precede_options_and_preserve_native_tables(
        self, tmp_path, capsys
    ):
        """!
        @brief Show findings first and keep native table layout.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        """
        with CheckOutput(tmp_path) as output:
            output.detail("Requirement: configured lint rules")
            status = output.command(
                [sys.executable, "-c", "print('All checks passed!')"],
                options=("repository rules",),
            )
            output.result("Lint", status == 0)
            output.detail("Table output:\nNLOC CCN\n  10   2", literal=True)
            output.section("Metrics", "PASS")
        console = capsys.readouterr().out
        assert "- Requirement: configured lint rules" in console
        tool = Path(sys.executable).name
        assert f"- {tool} output: All checks passed!" in console
        assert console.index(f"{tool} output:") < console.index("- Options:")
        rows = [row[2:-2].rstrip() for row in console.splitlines()]
        heading = rows.index("Table output:")
        assert rows[heading - 1] == ""
        assert rows[heading + 1 : heading + 3] == ["NLOC CCN", "  10   2"]
        assert all(len(row) == 120 for row in console.splitlines())

    def test_prose_keeps_continuations_and_truncation_marks(self, tmp_path):
        """!
        @brief Keep evidence indentation and omission marks intact.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        with CheckOutput(tmp_path) as output:
            output.detail("First finding\n  source context\n\n- Existing\n...")
            output.result("Lint", False)
        rows = [
            row[2:-2].rstrip() for row in output.path.read_text().splitlines()
        ]
        assert "- First finding" in rows
        assert "  source context" in rows and "" in rows
        assert "- Existing" in rows and "- - Existing" not in rows
        assert "..." in rows and "- ..." not in rows


class TestToolNames:
    """!
    @brief Check tool names against executable and Python module commands.
    """

    @pytest.mark.parametrize("verbose", [False, True])
    @pytest.mark.parametrize(
        "command, expected",
        [
            (["black", "--check", "."], "black"),
            (["/opt/tools/black", "--check", "."], "black"),
            ([r"C:\Tools\black.exe", "--check", "."], "black.exe"),
            (["python", "-m", "ruff", "check", "."], "ruff"),
            (["python", "-m", "black", "--check", "."], "black"),
            (["python3.12", "-I", "-m", "pip", "install", "."], "pip"),
            ([r"C:\Python312\python.exe", "-m", "black"], "black"),
            (["py", "-3.12", "-m", "venv", ".venv"], "venv"),
            (["python", "-W", "error", "-X", "dev", "-m", "black"], "black"),
            (["python", "-m", "pytest", "-m", "slow"], "pytest"),
            (["pytest", "-m", "slow"], "pytest"),
            (
                [
                    "python",
                    "-m",
                    "coverage",
                    "run",
                    "--branch",
                    "--source=src",
                    "-m",
                    "pytest",
                    "tests",
                    "-m",
                    "slow",
                ],
                "coverage / pytest",
            ),
            (["coverage", "run", "-m", "pytest"], "coverage / pytest"),
            (["python", "-m", "coverage", "json"], "coverage"),
            (["python", "-m", "coverage", "run", "script.py"], "coverage"),
            (["python", "script.py", "-m", "argument"], "python"),
            (["python", "--", "script.py", "-m", "argument"], "python"),
            (["python", "-c", "print('-m')", "-m", "argument"], "python"),
            (["python"], "python"),
        ],
    )
    def test_command_reports_its_actual_tool(
        self, tmp_path, monkeypatch, capsys, command, expected, verbose
    ):
        """!
        @brief Keep tool and output labels in sync with the command.
        @param tmp_path Temporary repo where the report log is written.
        @param monkeypatch Replace subprocess execution so tools need not be
        installed for these command examples.
        @param capsys Capture the printed report for comparison with the log.
        @param command Executable and arguments representing a tool invocation.
        @param expected Tool name that should appear in the report.
        @param verbose True for full output, or false for normal output.
        """
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args[0], 0, stdout="tool evidence"
            ),
        )
        with CheckOutput(tmp_path, verbose=verbose) as output:
            assert output.command(command) == 0
            output.result("Example", True)
        for report in (capsys.readouterr().out, output.path.read_text()):
            assert f"- Tool: {expected} " in report
            assert f"- {expected} output: tool evidence" in report
            assert all(len(line) == 120 for line in report.splitlines())

    def test_versions_follow_the_executed_modules(self, tmp_path):
        """!
        @brief Report versions of the modules used by a wrapped command.
        @param tmp_path Temporary working directory for coverage and the log.
        """
        with CheckOutput(tmp_path) as output:
            assert (
                output.command(
                    [sys.executable, "-m", "coverage", "run"],
                    options=["-m", "pytest", "--version"],
                )
                == 0
            )
            output.result("Example", True)
        log = output.path.read_text()
        for package in ("coverage", "pytest"):
            assert f"- Version: {package} {version(package)}" in log
        assert "- Version: ruff" not in log

    @pytest.mark.parametrize("module", ["venv", "ensurepip"])
    def test_standard_library_tools_use_the_python_version(
        self, tmp_path, module
    ):
        """!
        @brief Identify standard-library tools without a package-version lookup.
        @param tmp_path Temporary working directory for the report.
        @param module Standard-library module with a harmless help command.
        """
        with CheckOutput(tmp_path) as output:
            assert output.command([sys.executable, "-m", module, "--help"]) == 0
            output.result("Example", True)
        log = output.path.read_text()
        assert f"- Tool: {module}" in log
        assert f"- Version: Python {platform.python_version()}" in log
        assert "unavailable" not in log

    def test_versions_are_read_from_the_other_environment(self, tmp_path):
        """!
        @brief Read pip and Python versions from an environment with any name.
        @param tmp_path Temporary directory for an isolated Python installation.
        """
        directory = tmp_path / "custom python"
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(directory)
        python = builder.ensure_directories(directory).env_exec_cmd
        expected = subprocess.check_output(
            [python, "-m", "pip", "--version"], text=True
        ).split()
        with CheckOutput(tmp_path) as output:
            assert output.command([python, "-m", "pip", "--version"]) == 0
            output.result("Install", True)
            assert output.command([python, "-m", "venv", "--help"]) == 0
            output.result("Environment", True)
        log = output.path.read_text()
        assert f"- Version: pip {expected[1]}" in log
        assert f"- Version: Python {platform.python_version()}" in log
        assert "unavailable" not in log

    @pytest.mark.parametrize("missing", ["package", "executable"])
    def test_missing_metadata_does_not_invent_a_version(
        self, tmp_path, missing
    ):
        """!
        @brief Keep an unavailable version visible when its lookup cannot run.
        @param tmp_path Temporary working directory for the report.
        @param missing Select a missing package or a missing Python executable.
        """
        python = sys.executable if missing == "package" else "/absent/python"
        with CheckOutput(tmp_path) as output:
            assert output.command([python, "-m", "missing_quality_tool"]) != 0
            output.result("Example", False)
        log = output.path.read_text()
        assert "- Version: missing_quality_tool unavailable" in log

    def test_reported_options_are_passed_to_the_process(self, tmp_path):
        """!
        @brief Keep displayed arguments identical to the process inputs.
        @param tmp_path Temporary working directory for the command and log.
        """
        with CheckOutput(tmp_path) as output:
            assert (
                output.command(
                    [
                        sys.executable,
                        "-c",
                        "import sys\nprint(repr(sys.argv[1:]))",
                    ],
                    options=["--flag", "value with spaces"],
                )
                == 0
            )
            output.result("Example", True)
        log = output.path.read_text()
        assert "['--flag', 'value with spaces']" in log
        assert "- Options: --flag 'value with spaces'" in log
