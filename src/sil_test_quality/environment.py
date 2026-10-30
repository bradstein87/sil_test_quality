"""!
@brief Isolated Python setup for running precommit checks.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .configuration import CheckSettings
from .output import CheckOutput


class HookEnvironment:
    """!
    @brief Prepare and reuse the Python environment for checks.
    @details The cache depends on the Python runtime and setup files. A ready
    marker is written only after installation succeeds.
    """

    def __init__(self, root: Path) -> None:
        """!
        @brief Select the environment for the current repo setup.
        @details Checks the loaded version and reads setup files to choose a
        cache path. Environment creation happens in prepare.
        @param root Repo whose manifests supply dependencies and the requested
        checker version.
        @throws ValueError The loaded checker version does not match the
        repository request.
        """
        self.root = root.resolve()
        self.shared = Path(__file__).resolve().parents[2]
        settings = CheckSettings(self.root)
        self.report_width = settings.report_width
        if settings.version != __version__:
            raise ValueError(
                f"Expected sil_test_quality {settings.version}, "
                f"loaded {__version__}"
            )
        fingerprint = hashlib.sha256()
        for value in (
            str(self.root),
            str(self.shared),
            sys.platform,
            sys.version,
            str(Path(sys.base_prefix).resolve()),
        ):
            fingerprint.update(value.encode())
        paths = [
            self.root / "requirements.txt",
            self.root / "pyproject.toml",
            self.shared / "pyproject.toml",
            Path(__file__).with_name("baseline.toml"),
        ]
        if settings.version_file:
            paths.append(self.root / settings.version_file)
        for path in paths:
            fingerprint.update(path.read_bytes())
        self.directory = (
            self.root
            / ".precommit"
            / f"{sys.platform}-{fingerprint.hexdigest()[:16]}"
        )
        executable = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        self.python = self.directory / executable
        self.ready = self.directory / ".ready"

    def process_environment(self) -> dict[str, str]:
        """!
        @brief Prepare environment variables for checker processes.
        @return Variable dictionary for setup and check commands, selecting the
        hook Python and removing inherited Python/pip overrides.
        """
        environment = os.environ.copy()
        for name in (
            "PYTHONHOME",
            "PYTHONPATH",
            "PIP_TARGET",
            "PIP_PREFIX",
            "PIP_USER",
        ):
            environment.pop(name, None)
        environment["VIRTUAL_ENV"] = str(self.directory)
        environment["PATH"] = (
            str(self.python.parent) + os.pathsep + environment.get("PATH", "")
        )
        environment["PYTHONNOUSERSITE"] = "1"
        return environment

    def _commands(self) -> tuple[tuple[str, list[str]], ...]:
        """!
        @brief Prepare installation commands for the selected environment.
        @return Environment creation, dependency installation and project setup
        commands in execution order.
        """
        pip = [
            str(self.python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
        ]
        return (
            (
                "Environment",
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "venv",
                    "--clear",
                    str(self.directory),
                ],
            ),
            (
                "Dependencies",
                [*pip, "-r", "requirements.txt", "-e", str(self.shared)],
            ),
            ("Project", [*pip, "--no-deps", "-e", "."]),
        )

    def prepare(
        self,
        verbose: bool = False,
        brief: bool = False,
        report_width: int | None = None,
        wrap: bool = False,
    ) -> None:
        """!
        @brief Install the checker environment if it is not ready.
        @details Reuses completed setup. A failed install leaves no ready
        marker, so the next invocation retries. Setup output is saved in
        precommit-setup.log.
        @param verbose True to show all setup command output.
        @param brief True to show setup verdicts without their evidence.
        @param report_width Run-specific width, or None to use the repo setting.
        @param wrap Wrap long setup lines instead of clipping them.
        @throws subprocess.CalledProcessError Environment creation or a package
        installation command fails.
        """
        if self.ready.is_file() and self.python.is_file():
            return
        print("Preparing precommit environment...", flush=True)
        environment = self.process_environment()
        with CheckOutput(
            self.root,
            verbose,
            "precommit-setup.log",
            brief=brief,
            width=self.report_width if report_width is None else report_width,
            wrap=wrap,
        ) as output:
            for label, command in self._commands():
                output.start(label)
                if label == "Environment":
                    output.detail(f"- Setup Python: {sys.executable}")
                    output.detail(f"- Target environment: {self.directory}")
                    output.detail(f"- Target Python: {self.python}")
                status = output.command(command, env=environment)
                output.result(label, status == 0)
                if status:
                    raise subprocess.CalledProcessError(status, command)
        self.ready.touch()

    def run(
        self,
        fix: bool = False,
        verbose: bool = False,
        brief: bool = False,
        report_width: int | None = None,
        wrap: bool = False,
    ) -> int:
        """!
        @brief Run checks inside the selected Python environment.
        @details Starts a child process when outside the prepared environment.
        Inside it, runs RepositoryChecks directly to avoid repeated launches.
        @param fix Repair option forwarded to the checks.
        @param verbose Full-output option forwarded to setup and checks.
        @param brief Verdict-only option forwarded to setup and checks.
        @param report_width Run-specific width, or None to use the repo setting.
        @param wrap Wrap long console lines during setup and checks.
        @return Check exit status passed back to Git. Zero allows the commit.
        """
        if Path(sys.prefix).resolve() == self.directory:
            # Load checks only after their dependencies are installed.
            from .checks import RepositoryChecks  # noqa: PLC0415

            return RepositoryChecks(self.root).run(
                fix=fix,
                verbose=verbose,
                brief=brief,
                report_width=report_width,
                wrap=wrap,
            )
        self.prepare(
            verbose=verbose, brief=brief, report_width=report_width, wrap=wrap
        )
        command = [
            str(self.python),
            "-I",
            "-m",
            "sil_test_quality",
            "--root",
            str(self.root),
        ]
        if fix:
            command.append("--fix")
        if verbose:
            command.append("--verbose")
        elif brief:
            command.append("--brief")
        if report_width is not None:
            command.extend(["--report-width", str(report_width)])
        if wrap:
            command.append("--wrap")
        return subprocess.run(
            command, cwd=self.root, env=self.process_environment(), check=False
        ).returncode
