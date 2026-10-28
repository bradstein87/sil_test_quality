"""!
@brief Tests for isolated checker setup and environment reuse.
"""

import subprocess
import sys

import pytest

from sil_test_quality import __version__
from sil_test_quality.checks import RepositoryChecks
from sil_test_quality.environment import HookEnvironment


@pytest.fixture
def hook_project(tmp_path):
    """!
    @brief Create the manifests used by environment tests.
    @param tmp_path Pytest temporary directory for the sample files and
    artifacts.
    @return Temporary repo path supplying controlled setup inputs.
    """

    (tmp_path / "requirements.txt").write_text("pytest==9.0.1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "hook-example"\nversion = "1.0"\n'
        f'[tool.sil-test-quality]\nversion = "{__version__}"\n'
        'version-file = "version.py"\n'
    )
    (tmp_path / "version.py").write_text("VERSION = 1\n")
    return tmp_path


class EnvironmentInstaller:
    """!
    @brief Simulate setup commands without installing packages.
    """

    def __init__(self, environment):
        """!
        @brief Set up the fake installer and its failure controls.
        @param environment HookEnvironment whose Python marker this fake will
        create.
        """

        self.environment = environment
        self.commands = []
        self.fail_install = False
        self.check_status = 0

    def run(self, command, **options):
        """!
        @brief Record a setup command and simulate its result.
        @param command Subprocess argument list used to identify the simulated
        operation.
        @param options Subprocess options. The check flag separates setup from
        running checks.
        @return CompletedProcess containing the simulated command status.
        @throws subprocess.CalledProcessError The test configured a pip
        installation failure.
        """

        if "-c" in command:
            return subprocess.CompletedProcess(command, 0, stdout="pip 1.0")
        self.commands.append(command)
        if "venv" in command:
            self.environment.python.parent.mkdir(parents=True, exist_ok=True)
            self.environment.python.touch()
        if "pip" in command and self.fail_install:
            raise subprocess.CalledProcessError(1, command)
        status = self.check_status if not options["check"] else 0
        return subprocess.CompletedProcess(command, status)


class TestHookEnvironment:
    """!
    @brief Check setup, cache reuse and failed-install recovery.
    """

    @pytest.mark.parametrize(
        "fix, verbose, brief",
        [(False, False, False), (True, True, False), (False, False, True)],
    )
    def test_hook_prepares_its_own_environment_and_reuses_it(
        self, hook_project, monkeypatch, fix, verbose, brief
    ):
        """!
        @brief Prepare an environment once and reuse it for later checks.
        @param hook_project Fixture repo containing the manifests used to select
        a hook environment.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param fix Whether this scenario requests import and formatting repairs.
        @param verbose Full-output flag selected for this test scenario.
        @param brief Verdict-only flag selected for this test scenario.
        """

        environment = HookEnvironment(hook_project)
        installer = EnvironmentInstaller(environment)
        monkeypatch.setattr(subprocess, "run", installer.run)
        environment.prepare()
        installs = [
            command for command in installer.commands if "pip" in command
        ]
        assert len(installs) == 3
        assert all(
            command[0] == str(environment.python) for command in installs
        )
        assert environment.ready.is_file()
        rows = (hook_project / "artifacts/precommit-setup.log").read_text()
        evidence = "".join(
            "".join(row[2:-2].split())
            for row in rows.splitlines()
            if row.startswith("|")
        )
        assert "Targetenvironment:" + str(environment.directory) in evidence
        assert "TargetPython:" + str(environment.python) in evidence

        installer.commands.clear()
        installer.check_status = 7
        assert environment.run(fix=fix, verbose=verbose, brief=brief) == 7
        assert len(installer.commands) == 1
        assert installer.commands[0][0] == str(environment.python)
        assert ("--fix" in installer.commands[0]) == fix
        assert ("--verbose" in installer.commands[0]) == verbose
        assert ("--brief" in installer.commands[0]) == brief

    def test_incomplete_setup_stops_checks_and_can_be_retried(
        self, hook_project, monkeypatch
    ):
        """!
        @brief Stop on failed setup and retry it on the next invocation.
        @param hook_project Fixture repo containing the manifests used to select
        a hook environment.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """

        environment = HookEnvironment(hook_project)
        installer = EnvironmentInstaller(environment)
        installer.fail_install = True
        monkeypatch.setattr(subprocess, "run", installer.run)
        with pytest.raises(subprocess.CalledProcessError):
            environment.run()
        assert not environment.ready.exists()
        assert not any("sil_test_quality" in cmd for cmd in installer.commands)

        installer.fail_install = False
        environment.prepare()
        assert environment.ready.is_file()

    @pytest.mark.parametrize(
        "filename", ["requirements.txt", "pyproject.toml", "version.py"]
    )
    def test_setup_changes_select_a_fresh_environment(
        self, hook_project, filename
    ):
        """!
        @brief Select a new environment when setup inputs change.
        @param hook_project Fixture repo containing the manifests used to select
        a hook environment.
        @param filename Setup file to modify when testing cache selection.
        """

        original = HookEnvironment(hook_project).directory
        changed = hook_project / filename
        changed.parent.mkdir(parents=True, exist_ok=True)
        with changed.open("a") as file:
            file.write("\n# Updated project setup\n")
        assert HookEnvironment(hook_project).directory != original

    def test_active_environment_does_not_change_the_cache_or_leak_into_checks(
        self, hook_project, monkeypatch
    ):
        """!
        @brief Keep an unrelated shell environment out of the checks.
        @param hook_project Fixture repo containing the manifests used to select
        a hook environment.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """

        environment = HookEnvironment(hook_project)
        monkeypatch.setattr(
            sys, "prefix", str(hook_project / "unrelated-environment")
        )
        monkeypatch.setenv(
            "VIRTUAL_ENV", str(hook_project / "unrelated-environment")
        )
        for name in (
            "PYTHONHOME",
            "PYTHONPATH",
            "PIP_TARGET",
            "PIP_PREFIX",
            "PIP_USER",
        ):
            monkeypatch.setenv(name, "unrelated")
        assert HookEnvironment(hook_project).directory == environment.directory
        process = environment.process_environment()
        assert process["VIRTUAL_ENV"] == str(environment.directory)
        assert process["PATH"].startswith(str(environment.python.parent))
        assert not any(
            name in process
            for name in (
                "PYTHONHOME",
                "PYTHONPATH",
                "PIP_TARGET",
                "PIP_PREFIX",
                "PIP_USER",
            )
        )

    @pytest.mark.parametrize("verbose", [False, True])
    def test_prepared_child_runs_checks_without_relaunching(
        self, hook_project, monkeypatch, capsys, verbose
    ):
        """!
        @brief Run checks directly inside the prepared environment.
        @param hook_project Fixture repo containing the manifests used to select
        a hook environment.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param capsys Pytest capture used to check the printed Python output.
        @param verbose Full-output flag selected for this test scenario.
        """
        environment = HookEnvironment(hook_project)
        monkeypatch.setattr(sys, "prefix", str(environment.directory))
        calls = []
        monkeypatch.setattr(
            RepositoryChecks,
            "run",
            lambda self, **options: calls.append(options) or 3,
        )
        assert environment.run(fix=True, verbose=verbose) == 3
        assert calls == [{"fix": True, "verbose": verbose, "brief": False}]
        assert "Precommit checks using" not in capsys.readouterr().out

    def test_loaded_version_must_match_requested_version(self, hook_project):
        """!
        @brief Reject a loaded checker with the wrong version.
        @param hook_project Fixture repo containing the manifests used to select
        a hook environment.
        """
        manifest = hook_project / "pyproject.toml"
        manifest.write_text(
            manifest.read_text().replace(
                f'version = "{__version__}"', 'version = "0.2.0"'
            )
        )
        with pytest.raises(ValueError, match=f"loaded {__version__}"):
            HookEnvironment(hook_project)
