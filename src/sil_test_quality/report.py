"""!
@brief Repo information and input consistency in the report output.
"""

import platform
import subprocess
import time
from datetime import datetime, timezone

from sil_test_quality import __version__
from sil_test_quality import configuration as policy
from sil_test_quality.output import CheckOutput
from sil_test_quality.source import ProjectSource


class QualityReport:
    """!
    @brief Record which repo state produced the check results.
    @details Create one instance per run. Construction saves the initial file
    fingerprint and Git revision. The emit method compares them afterward.
    """

    def __init__(self, source: ProjectSource) -> None:
        """!
        @brief Capture repo state before the checks start.
        @param source ProjectSource supplying the repo location and files to
        fingerprint.
        """

        self.source = source
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.clock = time.monotonic()
        self.fingerprint = source.fingerprint()
        self.commit = self.git("rev-parse", "HEAD")
        self.branch = self.git("branch", "--show-current") or "detached HEAD"
        status = self.git("status", "--porcelain")
        self.tree = (
            "unavailable"
            if status == "unknown"
            else "dirty"
            if status
            else "clean"
        )

    def git(self, *arguments: str) -> str:
        """!
        @brief Read Git information for the report.
        @param arguments Git command words, such as rev-parse and HEAD, run in
        this repo.
        @return Trimmed command output, or unknown if Git fails or times out.
        """

        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.source.root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            return (
                result.stdout.strip() if result.returncode == 0 else "unknown"
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"

    def begin(self, output: CheckOutput) -> None:
        """!
        @brief Print the repo and runtime that produced this report.
        @param output Report recorder receiving this check's evidence and
        results.
        """
        output.start("Repository")
        output.detail(f"- Repository: {self.source.root.name}")
        output.detail(f"- Shared checks: sil_test_quality {__version__}")
        output.detail(f"- Branch: {self.branch}, working tree: {self.tree}")
        output.detail(f"- HEAD: {self.commit}")
        output.detail(f"- Started (UTC): {self.started}")
        output.detail(
            f"- Runtime: {platform.system()}, "
            f"Python {platform.python_version()}"
        )
        output.detail("- Scope: maintained files, mypy src/, pytest tests/")
        excluded = [
            f"- Legacy excluded: {name}" for name in self.source.exclusions
        ]
        output.detail(
            "\n".join(excluded),
            normal="\n".join(excluded[: policy.NORMAL_ROWS]),
        )
        output.detail(f"- Legacy exclusions: {len(excluded)} files")
        output.section("Repository", "")

    def emit(self, output: CheckOutput, suppressions: list[str]) -> None:
        """!
        @brief Check that source inputs stayed unchanged during checks.
        @details A changed file fingerprint or Git revision fails Consistency.
        Generated logs are outside the fingerprint.
        @param output Report recorder receiving this check's evidence and
        results.
        @param suppressions Inline exceptions found by source inspection, listed
        in the report.
        """
        output.start("Consistency")
        after = self.source.fingerprint()
        commit = self.git("rev-parse", "HEAD")
        unchanged = self.fingerprint == after and self.commit == commit
        output.detail("- Requirement: checked inputs remain unchanged")
        output.detail(f"- Input SHA256 before: {self.fingerprint}")
        output.detail(f"- Input SHA256 after:  {after}")
        output.detail(f"- HEAD before: {self.commit}")
        output.detail(f"- HEAD after:  {commit}")
        rows = [f"- Suppression: {item}" for item in suppressions]
        output.detail(
            "\n".join(rows), normal="\n".join(rows[: policy.NORMAL_ROWS])
        )
        output.detail(f"- Suppressions: {len(rows)}")
        output.detail(f"- Elapsed: {time.monotonic() - self.clock:.1f} seconds")
        if not unchanged:
            output.detail("INVALIDATED: checked inputs changed")
        output.result("Consistency", unchanged)
