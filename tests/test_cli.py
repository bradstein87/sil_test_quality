"""!
@brief Tests for command-line report modes and startup failures.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from sil_test_quality import cli
from sil_test_quality.checks import RepositoryChecks
from sil_test_quality.output import CheckOutput

ROOT = Path(__file__).resolve().parents[1]


class TestReportModes:
    """!
    @brief Check report choices and command-line error handling.
    """

    @pytest.mark.parametrize(
        "width,wrap", [(0, False), (120, False), (160, True), (0, True)]
    )
    @pytest.mark.parametrize("mode", ["brief", "normal", "verbose"])
    def test_console_selection_and_complete_log(
        self, tmp_path, capsys, mode, width, wrap
    ):
        """!
        @brief Keep the full log regardless of console detail level.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        @param mode Report mode under test: brief, normal or verbose.
        @param width Requested width, including unframed output.
        @param wrap Whether console lines should wrap within the borders.
        """
        with CheckOutput(
            tmp_path,
            verbose=mode == "verbose",
            brief=mode == "brief",
            width=width,
            wrap=wrap,
        ) as output:
            output.detail(
                "row one\nrow two\nrow three\nrow four",
                normal="row one\nrow two\nrow three",
            )
            text = "long-path/" * 40 + "evidence_end"
            output.detail(text)
            output.result("Example check", False)
            assert output.finish() == 1
        console = capsys.readouterr().out
        assert ("row one" in console) == (mode != "brief")
        assert ("row four" in console) == (mode == "verbose")
        log = output.path.read_text()
        assert "row four" in log
        assert text in "".join(
            line[2:-2].rstrip() if line.startswith("|") else line
            for line in log.splitlines()
        )
        assert ("evidence_end" in console) == (
            mode != "brief" and (wrap or width == 0)
        )
        if width and not wrap and mode != "brief":
            assert "... |" in console
        if width:
            assert all(len(line) in (0, width) for line in console.splitlines())
        else:
            assert "Example check  [FAIL]" in console
            assert not console.startswith("+")

    @pytest.mark.parametrize(
        "configured,override", [(0, None), (160, None), (160, 0)]
    )
    def test_run_option_overrides_the_consumer_width(
        self, tmp_path, monkeypatch, capsys, configured, override
    ):
        """!
        @brief Apply the chosen width before reporting a configuration failure.
        @param tmp_path Repo whose lint policy deliberately fails validation.
        @param monkeypatch Skip setup to exercise the report directly.
        @param capsys Capture the final report from the CLI.
        @param configured Width in the consuming pyproject.toml.
        @param override Run-specific width, or None to use configuration.
        """
        (tmp_path / "pyproject.toml").write_text(
            '[tool.sil-test-quality]\nversion = "0.2.0"\n'
            f"report-width = {configured}\n"
            '[tool.ruff.lint]\nignore = ["F401"]\n'
        )
        args = ["sil-test-quality"]
        if override is not None:
            args += ["--report-width", str(override)]
        monkeypatch.setattr(cli.sys, "argv", args)
        monkeypatch.setattr(cli.HookEnvironment, "__init__", lambda *args: None)
        monkeypatch.setattr(
            cli.HookEnvironment,
            "run",
            lambda self, **kwargs: RepositoryChecks(tmp_path).run(**kwargs),
        )
        assert cli.main(tmp_path) == 1
        console = capsys.readouterr().out
        width = configured if override is None else override
        if width:
            assert all(len(row) in (0, width) for row in console.splitlines())
        else:
            assert "Settings  [FAIL]" in console
        assert "report-width" not in console

    @pytest.mark.parametrize(
        "args,brief,verbose",
        [
            ([], False, False),
            (["--brief"], True, False),
            (["--normal", "--wrap"], False, False),
            (["--verbose"], False, True),
            (["-v"], False, True),
        ],
    )
    def test_cli_modes(self, tmp_path, monkeypatch, args, brief, verbose):
        """!
        @brief Pass the selected report mode to the checker environment.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param args Command-line arguments supplied to the CLI for this
        scenario.
        @param brief Expected brief flag forwarded to HookEnvironment.run.
        @param verbose Expected verbose flag forwarded to HookEnvironment.run.
        """
        calls = []
        monkeypatch.setattr(cli.sys, "argv", ["sil-test-quality", *args])
        monkeypatch.setattr(
            cli.HookEnvironment,
            "run",
            lambda self, **kwargs: calls.append(kwargs) or 7,
        )
        monkeypatch.setattr(cli.HookEnvironment, "__init__", lambda *args: None)
        assert cli.main(tmp_path) == 7
        assert calls == [
            {
                "fix": False,
                "brief": brief,
                "verbose": verbose,
                "report_width": None,
                "wrap": "--wrap" in args,
            }
        ]

    @pytest.mark.parametrize(
        "args",
        [["--brief", "--verbose"], ["--brief", "--normal"], ["--normal", "-v"]],
    )
    def test_cli_rejects_conflicting_modes(self, monkeypatch, args):
        """!
        @brief Reject conflicting report-mode flags.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param args Conflicting report options supplied together.
        """
        monkeypatch.setattr(cli.sys, "argv", ["sil-test-quality", *args])
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 2

    @pytest.mark.parametrize(
        "width", [[], ["--report-width", "0"], ["--report-width=160"]]
    )
    @pytest.mark.parametrize("mode", ["--brief", "--normal", "--verbose"])
    def test_git_mode_overrides_local_verbose_setting(
        self, tmp_path, mode, width
    ):
        """!
        @brief Let explicit hook flags override the local verbose setting.
        @param width Width arguments supplied to the Git hook.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param mode Report mode under test: brief, normal or verbose.
        """
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools/precommit.py").write_text(
            'import sys\nprint("ARGS:", sys.argv[1:])\nsys.exit(7)\n'
        )
        hooks = tmp_path / ".githooks"
        hooks.mkdir()
        shutil.copy2(ROOT / ".githooks/pre-commit", hooks / "pre-commit")
        command = [
            "git",
            "-c",
            "core.hooksPath=.githooks",
            "-c",
            "precommit.verbose=true",
            "hook",
            "run",
            "pre-commit",
            "--",
        ]
        result = subprocess.run(
            [*command, mode, *width, "--wrap"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 7
        expected = (
            [mode]
            + (["--report-width", width[-1].split("=")[-1]] if width else [])
            + ["--wrap"]
        )
        assert f"ARGS: {expected!r}" in result.stdout + result.stderr
        result = subprocess.run(
            [*command, "--brief", "--verbose"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "Choose one report mode" in result.stderr

    @pytest.mark.parametrize("writable_log", [False, True])
    def test_setup_failure_replaces_stale_success(
        self, tmp_path, monkeypatch, capsys, writable_log
    ):
        """!
        @brief Report setup failure even when a new log cannot be written.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param capsys Pytest capture used to check the printed Python output.
        @param writable_log Whether the artifacts path allows writing the
        failure log.
        """
        artifacts = tmp_path / "artifacts"
        if writable_log:
            artifacts.mkdir()
            (artifacts / "precommit.log").write_text("Old success")
        else:
            artifacts.write_text("Directory is unavailable")
        monkeypatch.setattr(cli.sys, "argv", ["sil-test-quality"])
        # No project version pin: environment construction must reject setup.
        assert cli.main(tmp_path) == 1
        captured = capsys.readouterr()
        assert "checks could not finish" in captured.err
        assert "NOT RUN" in captured.err
        assert "precommit-setup.log" in captured.out
        if writable_log:
            log = (artifacts / "precommit.log").read_text()
            assert "Old success" not in log and "NOT RUN" in log


class TestPrecommitCommand:
    """!
    @brief Check failure reporting when the hook cannot start.
    """

    @pytest.mark.parametrize("help_option", ["-h", "--help"])
    def test_help_skips_environment_setup(
        self, tmp_path, monkeypatch, capsys, help_option
    ):
        """!
        @brief Show command help without preparing a checker environment.
        @param tmp_path Empty repository with no checker configuration.
        @param monkeypatch Pytest helper for setting command-line arguments.
        @param capsys Captured help output.
        @param help_option Short or long help option to invoke.
        """
        monkeypatch.setattr(cli.sys, "argv", ["sil-test-quality", help_option])
        assert cli.main(tmp_path) == 0
        help_text = capsys.readouterr().out
        assert "--fix" in help_text and "--root" in help_text
        assert "@brief" not in help_text
        assert list(tmp_path.iterdir()) == []

    def test_root_override_preserves_fix_and_failure_status(
        self, tmp_path, monkeypatch
    ):
        """!
        @brief Honor the selected repo and return its failing check status.
        @param tmp_path Parent of the selected repository and bootstrap default.
        @param monkeypatch Pytest helper for recording checker calls.
        """
        selected = tmp_path / "repo with spaces"
        calls = []
        monkeypatch.setattr(
            cli.sys,
            "argv",
            ["sil-test-quality", "--root", str(selected), "--fix", "-v"],
        )
        monkeypatch.setattr(
            cli.HookEnvironment,
            "__init__",
            lambda self, root: calls.append(root),
        )
        monkeypatch.setattr(
            cli.HookEnvironment,
            "run",
            lambda self, **options: calls.append(options) or 1,
        )
        assert cli.main(tmp_path) == 1
        assert calls == [
            selected.resolve(),
            {
                "fix": True,
                "verbose": True,
                "brief": False,
                "report_width": None,
                "wrap": False,
            },
        ]

    def test_setup_failure_replaces_old_success_evidence(
        self, tmp_path, monkeypatch
    ):
        """!
        @brief Replace old pass evidence when setup fails.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """

        monkeypatch.setattr(cli.sys, "argv", ["precommit.py"])

        def fail(*args, **kwargs):
            """!
            @brief Simulate setup failing before any checks run.
            @param args Constructor arguments accepted by this failing
            substitute.
            @param kwargs Constructor keyword arguments accepted without use.
            @throws RuntimeError Always raised to simulate failed dependency
            installation.
            """

            raise RuntimeError("Dependency installation failed")

        monkeypatch.setattr(cli, "HookEnvironment", fail)
        log = tmp_path / "artifacts/precommit.log"
        log.parent.mkdir()
        log.write_text("Automated outcome: PASS\n")
        assert cli.main(tmp_path) == 1
        assert "PASS" not in log.read_text()
        assert "[NOT RUN]" in log.read_text()
