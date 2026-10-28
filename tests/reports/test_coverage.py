"""!
@brief Tests for full and normal coverage report tables.
"""

from sil_test_quality.reports.coverage import CoverageReport


class TestCoverageReport:
    """!
    @brief Check coverage ordering, shortening and exclusions.
    """

    def test_native_table_is_statement_only_sorted_and_truncated(
        self, tmp_path
    ):
        """!
        @brief Put the lowest-covered files first in the normal table.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        files = {}
        for name, executed in [
            ("best", [1, 2, 3, 4]),
            ("middle", [1, 2, 3]),
            ("worst", []),
            ("next", [1, 2]),
        ]:
            path = tmp_path / f"{name}.py"
            path.write_text("a = 1\nb = 2\nc = 3\nd = 4\n")
            files[path.name] = {"executed_lines": executed}
        full, normal = CoverageReport(tmp_path).render({"files": files})
        assert "100.00%" in full and "75.00%" in normal and "0.00%" in normal
        assert normal.index("worst.py") < normal.index("next.py")
        assert normal.index("next.py") < normal.index("middle.py")
        assert "best.py" not in normal and "best.py" in full
        assert "TOTAL" in normal and "Missing" in normal
        assert "Branch" not in full and "..." in normal
        assert not (tmp_path / ".coverage").exists()

    def test_project_exclusions_are_retained(self, tmp_path):
        """!
        @brief Keep configured statement exclusions in the coverage table.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        (tmp_path / "pyproject.toml").write_text(
            '[tool.coverage.report]\nexclude_lines = ["EXCLUDE_ME"]\n'
        )
        (tmp_path / "sample.py").write_text("a = 1\nb = 2  # EXCLUDE_ME\n")
        full, normal = CoverageReport(tmp_path).render(
            {"files": {"sample.py": {"executed_lines": [1]}}}
        )
        assert "100.00%" in full and full.strip() == normal
