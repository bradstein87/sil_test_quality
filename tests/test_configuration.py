"""!
@brief Tests for supported repo settings and invalid configuration.
"""

import pytest

from sil_test_quality.configuration import CheckSettings


class TestCheckSettings:
    """!
    @brief Check configuration defaults and rejected settings.
    """

    def test_defaults_and_repository_specific_settings(self, tmp_path):
        """!
        @brief Load defaults and supported repo settings.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        (tmp_path / "pyproject.toml").write_text(
            '[tool.sil-test-quality]\nversion = "0.1.0"\n'
        )
        defaults = CheckSettings(tmp_path)
        assert defaults.version == "0.1.0"
        assert defaults.test_label == "Software tests"
        assert defaults.coverage_omit == []
        (tmp_path / "pyproject.toml").write_text(
            '[tool.sil-test-quality]\nversion = "0.2.0"\n'
            'test-label = "Library tests"\n'
            'coverage-omit = ["src/product_cases/*"]\n'
            'version-file = "src/example/__init__.py"\n'
        )
        configured = CheckSettings(tmp_path)
        assert configured.version == "0.2.0"
        assert configured.test_label == "Library tests"
        assert configured.coverage_omit == ["src/product_cases/*"]
        assert configured.version_file == "src/example/__init__.py"

    @pytest.mark.parametrize(
        "manifest", [None, "", "[tool.sil-test-quality]\n"]
    )
    def test_missing_version_is_rejected(self, tmp_path, manifest):
        """!
        @brief Require an explicit checker version in every repo.
        @param tmp_path Temporary repo with missing version configuration.
        @param manifest TOML content, or None to leave the manifest absent.
        """
        if manifest is not None:
            (tmp_path / "pyproject.toml").write_text(manifest)
        with pytest.raises(ValueError, match="version must be an exact"):
            CheckSettings(tmp_path)

    @pytest.mark.parametrize(
        "settings",
        [
            'version = "latest"',
            "version = 1",
            'test-label = " "',
            "test-label = []",
            'coverage-omit = "src/*"',
            "coverage-omit = [1]",
            'coverage-omit = ["../elsewhere/*"]',
            'version-file = "../version.py"',
            "version-file = 3",
            'source = "https://site-specific.example/checks"',
        ],
    )
    def test_invalid_or_site_specific_policy_is_rejected(
        self, tmp_path, settings
    ):
        """!
        @brief Reject unsupported settings and paths outside the repo.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param settings Invalid TOML setting written into the test repo to check
        rejection.
        """
        (tmp_path / "pyproject.toml").write_text(
            "[tool.sil-test-quality]\n"
            + (
                ""
                if settings.startswith("version =")
                else 'version = "0.1.0"\n'
            )
            + settings
            + "\n"
        )
        with pytest.raises(ValueError):
            CheckSettings(tmp_path)

    def test_invalid_table_is_rejected(self, tmp_path):
        """!
        @brief Reject a checker section that is not a TOML table.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        (tmp_path / "pyproject.toml").write_text(
            "[tool]\nsil-test-quality = 12\n"
        )
        with pytest.raises(ValueError, match="table"):
            CheckSettings(tmp_path)
