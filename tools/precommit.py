"""!
@brief Locate the shared checker package and start the Git hook.
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


class QualitySource:
    """!
    @brief Find the checker version requested by the consuming repo.
    @details Location precedence is SIL_TEST_QUALITY_SOURCE, then Git
    sil-test-quality.source, then the sibling checkout. An invalid override
    fails without trying a different source.
    """

    def __init__(self, root: Path) -> None:
        """!
        @brief Read the requested checker version and location.
        @param root Consuming repo whose manifest and local settings select the
        checker.
        @throws ValueError The requested version is not exact or the Git source
        setting cannot be read.
        """
        self.root = root.resolve()
        data = tomllib.loads((self.root / "pyproject.toml").read_text())
        self.version = (
            data.get("tool", {}).get("sil-test-quality", {}).get("version")
        )
        if not isinstance(self.version, str) or not re.fullmatch(
            r"\d+\.\d+\.\d+", self.version
        ):
            raise ValueError(
                "Set tool.sil-test-quality.version to an exact X.Y.Z"
            )
        configured = subprocess.run(
            ["git", "config", "--get", "sil-test-quality.source"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if configured.returncode not in (0, 1):
            raise ValueError("Could not read Git sil-test-quality.source")
        self.source = (
            os.environ.get("SIL_TEST_QUALITY_SOURCE")
            or configured.stdout.strip()
            or str(self.root.parent / "sil_test_quality")
        )

    def checkout(self) -> Path:
        """!
        @brief Find and validate the shared checker checkout.
        @return Absolute package directory whose src path main adds for imports.
        @throws ValueError The package is missing, has the wrong
        identity/version, or lacks its CLI.
        """
        remote = self.source.startswith(
            ("https://", "http://", "ssh://", "file://", "git@")
        )
        path = self._clone() if remote else Path(self.source).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        manifest = path / "pyproject.toml"
        if not manifest.is_file():
            raise ValueError(
                "Shared checks not found. Set git config --local "
                "sil-test-quality.source <checkout-path-or-Git-URL>"
            )
        project = tomllib.loads(manifest.read_text()).get("project", {})
        if (
            project.get("name") != "sil_test_quality"
            or project.get("version") != self.version
            or not (path / "src/sil_test_quality/cli.py").is_file()
        ):
            raise ValueError(
                f"Expected sil_test_quality {self.version} - "
                "the configured checkout does not match"
            )
        return path

    def _clone(self) -> Path:
        """!
        @brief Reuse or download the requested Git release.
        @details Caches by source URL and requested version. A cache miss
        downloads tag vX.Y.Z into a temporary directory before making it
        available.
        @return Cached checkout directory for package validation and import.
        @throws subprocess.CalledProcessError Git cannot clone the requested
        source/tag or verify the release tag.
        """
        key = hashlib.sha256(self.source.encode()).hexdigest()[:16]
        cache = self.root / ".precommit" / "sources"
        target = cache / f"{key}-{self.version}"
        if target.is_dir():
            return target
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            checkout = Path(temporary) / "checkout"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--depth",
                    "1",
                    "--branch",
                    f"v{self.version}",
                    "--",
                    self.source,
                    str(checkout),
                ],
                cwd=self.root,
                check=True,
            )
            subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/tags/v{self.version}"],
                cwd=checkout,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            checkout.rename(target)
        return target


def main() -> int:
    """!
    @brief Start the hook using the selected shared checker.
    @return Shared checker exit status, or one if loading it fails.
    """
    root = Path(__file__).resolve().parents[1]
    try:
        source = QualitySource(root).checkout()
        sys.path.insert(0, str(source / "src"))
        # The selected checkout must be on the import path first.
        from sil_test_quality.cli import main as run_checks  # noqa: PLC0415

        return run_checks(root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        message = f"Precommit FAILED: shared checker setup. {error}"
        print(message, file=sys.stderr)
        log = root / "artifacts/precommit.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(message + "\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
