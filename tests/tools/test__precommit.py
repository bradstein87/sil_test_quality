"""!
@brief Tests for shared-checker selection by the repo bootstrap.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.precommit import QualitySource


@pytest.fixture
def project(tmp_path, monkeypatch):
    """!
    @brief Create a consumer repo with isolated local settings.
    @param tmp_path Pytest temporary directory for the sample files and
    artifacts.
    @param monkeypatch Pytest fixture for replacing dependencies and restoring
    them afterward.
    @return Temporary Git repo path used to test checker version and source
    choices.
    """
    monkeypatch.delenv("SIL_TEST_QUALITY_SOURCE", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in list(os.environ):
        if key.startswith("GIT_") and key not in (
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
        ):
            monkeypatch.delenv(key)
    root = tmp_path / "consumer"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.sil-test-quality]\nversion = "0.1.0"\n'
    )
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    return root


@pytest.fixture
def shared(tmp_path):
    """!
    @brief Create a minimal shared-package checkout for the tests.
    @param tmp_path Pytest temporary directory for the sample files and
    artifacts.
    @return Sibling package path with identity and entry-point files for
    validation.
    """
    path = tmp_path / "sil_test_quality"
    (path / "src/sil_test_quality").mkdir(parents=True)
    (path / "src/sil_test_quality/cli.py").write_text("# Example shared CLI\n")
    (path / "pyproject.toml").write_text(
        '[project]\nname = "sil_test_quality"\nversion = "0.1.0"\n'
    )
    return path


class TestQualitySource:
    """!
    @brief Check local overrides and cached checker releases.
    """

    def test_peer_checkout_is_default(self, project, shared):
        """!
        @brief Use the sibling checkout when no override is configured.
        @param project Temporary consuming Git repo used to test source and
        version settings.
        @param shared Minimal shared-package fixture used to validate checkout
        selection.
        """
        assert QualitySource(project).checkout() == shared

    def test_git_override_survives_bootstrap_replacement(
        self, project, shared, tmp_path
    ):
        """!
        @brief Keep local source settings when the bootstrap is replaced.
        @param project Temporary consuming Git repo used to test source and
        version settings.
        @param shared Minimal shared-package fixture used to validate checkout
        selection.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        alternate = tmp_path / "internal checkout with spaces"
        shared.rename(alternate)
        subprocess.run(
            [
                "git",
                "config",
                "--local",
                "sil-test-quality.source",
                str(alternate),
            ],
            cwd=project,
            check=True,
        )
        (project / "tools").mkdir()
        original = Path(__file__).resolve().parents[2] / "tools/precommit.py"
        shutil.copyfile(original, project / "tools/precommit.py")
        assert QualitySource(project).checkout() == alternate
        shutil.copyfile(original, project / "tools/precommit.py")
        assert QualitySource(project).checkout() == alternate

    def test_environment_override_takes_priority_and_never_falls_back(
        self, project, shared, monkeypatch
    ):
        """!
        @brief Honor the explicit source without silently falling back.
        @param project Temporary consuming Git repo used to test source and
        version settings.
        @param shared Minimal shared-package fixture used to validate checkout
        selection.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """
        monkeypatch.setenv("SIL_TEST_QUALITY_SOURCE", "missing")
        with pytest.raises(ValueError, match="Shared checks not found"):
            QualitySource(project).checkout()
        monkeypatch.setenv("SIL_TEST_QUALITY_SOURCE", "../sil_test_quality")
        assert QualitySource(project).checkout() == shared

    def test_wrong_package_version_and_missing_entrypoint_are_rejected(
        self, project, shared
    ):
        """!
        @brief Reject the wrong package, version or missing entry point.
        @param project Temporary consuming Git repo used to test source and
        version settings.
        @param shared Minimal shared-package fixture used to validate checkout
        selection.
        """
        manifest = shared / "pyproject.toml"
        original = manifest.read_text()
        for changed in (
            original.replace("0.1.0", "0.2.0"),
            original.replace("sil_test_quality", "another-package"),
        ):
            manifest.write_text(changed)
            with pytest.raises(ValueError, match="does not match"):
                QualitySource(project).checkout()
        manifest.write_text(original)
        (shared / "src/sil_test_quality/cli.py").unlink()
        with pytest.raises(ValueError, match="does not match"):
            QualitySource(project).checkout()

    @pytest.mark.parametrize("version", ["latest", "../other", "0.1", ""])
    def test_manifest_requires_exact_version(self, project, version):
        """!
        @brief Require an exact checker version in the manifest.
        @param project Temporary consuming Git repo used to test source and
        version settings.
        @param version Invalid requested version written into the consumer
        manifest.
        """
        (project / "pyproject.toml").write_text(
            f'[tool.sil-test-quality]\nversion = "{version}"\n'
        )
        with pytest.raises(ValueError, match="exact X.Y.Z"):
            QualitySource(project)

    def test_git_source_uses_version_tag_and_cached_checkout(
        self, project, shared, monkeypatch
    ):
        """!
        @brief Fetch a release tag once and reuse its cached checkout.
        @param project Temporary consuming Git repo used to test source and
        version settings.
        @param shared Minimal shared-package fixture used to validate checkout
        selection.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        """
        subprocess.run(["git", "init", "--quiet", str(shared)], check=True)
        subprocess.run(["git", "add", "."], cwd=shared, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "Fixture",
            ],
            cwd=shared,
            check=True,
        )
        subprocess.run(["git", "tag", "v0.1.0"], cwd=shared, check=True)
        monkeypatch.setenv("SIL_TEST_QUALITY_SOURCE", shared.as_uri())
        cached = QualitySource(project).checkout()
        assert cached != shared
        assert (cached / "src/sil_test_quality/cli.py").is_file()
        shared.rename(shared.with_name("remote-offline"))
        assert QualitySource(project).checkout() == cached
        shared.with_name("remote-offline").rename(shared)
        (project / "pyproject.toml").write_text(
            '[tool.sil-test-quality]\nversion = "0.2.0"\n'
        )
        with pytest.raises(subprocess.CalledProcessError):
            QualitySource(project).checkout()
        subprocess.run(["git", "branch", "v0.2.0"], cwd=shared, check=True)
        with pytest.raises(subprocess.CalledProcessError):
            QualitySource(project).checkout()
        assert len(list((project / ".precommit/sources").iterdir())) == 1
