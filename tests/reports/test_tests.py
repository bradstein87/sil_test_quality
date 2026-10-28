"""!
@brief Tests for normal-mode pytest result summaries.
"""

from sil_test_quality.reports.tests import TestReport as PytestReport


class TestPytestReport:
    """!
    @brief Check pytest result priorities and diagnostic fallback.
    """

    def test_errors_and_failures_replace_progress_with_reasons(self):
        """!
        @brief Use failure reasons instead of duplicate progress results.
        """
        text = "\n".join(
            [
                "platform linux -- Python 3.12.15",
                "rootdir: /project",
                "configfile: pyproject.toml",
                "plugins: example",
                "collected 7 items",
                *[
                    f"tests/test_a.py::TestA::test_{i} PASSED [10%]"
                    for i in range(4)
                ],
                "tests/test_a.py::TestA::test_4 SKIPPED (offline) [70%]",
                "tests/test_a.py::TestA::test_5 FAILED [85%]",
                "tests/test_a.py::TestA::test_6 ERROR [100%]",
                "FAILED tests/test_a.py::TestA::test_5 - "
                "AssertionError: expected 2",
                "ERROR tests/test_a.py::TestA::test_6 - "
                "RuntimeError: cannot connect",
                "SKIPPED [1] tests/test_a.py:20: offline",
                "=== 1 failed, 4 passed, 1 skipped, 1 error in 0.42s ===",
            ]
        )
        full, normal = PytestReport().render(text)
        assert full == text
        assert normal.startswith("=== 1 failed")
        assert normal.index("RuntimeError") < normal.index("AssertionError")
        assert "offline" in normal and "PASSED" not in normal
        assert "..." in normal
        assert "collected 7 items" in normal

    def test_passes_and_no_test_collection(self):
        """!
        @brief Handle passing runs and errors before test collection.
        """
        text = "\n".join(f"test_a.py::test_{i} PASSED [50%]" for i in range(4))
        full, normal = PytestReport().render(text)
        assert full == text and "test_3" not in normal
        assert "..." in normal
        text = "ERROR: file or directory not found: tests"
        assert PytestReport().render(text) == (text, text)
