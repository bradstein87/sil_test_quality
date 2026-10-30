"""!
@brief Tests for normal-mode pytest result summaries.
"""

import pytest

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
                "rootdir: /project",
                "configfile: pyproject.toml",
                "testpaths: tests",
                "collected 4 items",
                "tests/test_a.py::TestA::test_0 PASSED [10%]",
                "tests/test_a.py::TestA::test_4 SKIPPED (offline) [70%]",
                "tests/test_a.py::TestA::test_5 FAILED [85%]",
                "tests/test_a.py::TestA::test_6 ERROR [100%]",
                "FAILED tests/test_a.py::TestA::test_5 - "
                "AssertionError: expected 2",
                "ERROR tests/test_a.py::TestA::test_6 - "
                "RuntimeError: cannot connect",
                "SKIPPED [1] tests/test_a.py:20: offline",
                "=== 1 failed, 1 passed, 1 skipped, 1 error in 0.42s ===",
            ]
        )
        full, normal = PytestReport().render(text)
        assert full == text
        assert normal.startswith(
            "rootdir: /project\nconfigfile: pyproject.toml"
        )
        assert normal.index("RuntimeError") < normal.index("AssertionError")
        assert "offline" in normal and "test_0 PASSED" not in normal
        assert "testpaths: tests\ncollected 4 items" in normal
        assert normal.index("...") < normal.index("=== 1 failed")
        assert normal.endswith(text.splitlines()[-1])

    def test_passes_and_no_test_collection(self):
        """!
        @brief Handle passing runs and errors before test collection.
        """
        text = "\n".join(
            [f"test_a.py::test_{i} PASSED [50%]" for i in range(4)]
            + ["=== 4 passed in 0.42s ==="]
        )
        full, normal = PytestReport().render(text)
        assert full == text and normal.endswith("=== 4 passed in 0.42s ===")
        assert "test_a.py::test_0 PASSED [50%]" in normal
        assert "test_2 PASSED" in normal and "test_3 PASSED" not in normal
        assert normal.index("...") < normal.index("=== 4 passed")
        text = "ERROR: file or directory not found: tests"
        assert PytestReport().render(text) == (text, text)
        text = "ERROR tests/test_broken.py - SyntaxError: invalid syntax"
        assert PytestReport().render(text) == (text, text)

    @pytest.mark.parametrize(
        "statuses, expected",
        [
            (["PASSED", "XFAIL", "SKIPPED", "XPASS", "FAILED"], [4, 3, 2]),
            (["PASSED", "FAILED", "PASSED", "PASSED"], [1, 0, 2]),
        ],
    )
    def test_normal_prioritizes_native_results(self, statuses, expected):
        """!
        @brief Keep the most relevant native results without rewriting them.
        @param statuses Native outcomes in pytest's execution order.
        @param expected Result indexes that should appear in the preview.
        """
        lines = [
            f"test_a.py::test_{i} {outcome} [20%]"
            for i, outcome in enumerate(statuses)
        ]
        text = "\n".join(lines)
        full, normal = PytestReport().render(text)
        assert full == text
        assert normal.splitlines() == [*(lines[i] for i in expected), "..."]

    def test_teardown_and_parameterized_summaries_are_counted_once(self):
        """!
        @brief Retain call and teardown outcomes without counting them twice.
        """
        node = "tests/test_example.py::TestExample::test_case[before - after]"
        text = "\n".join(
            [
                f"{node} PASSED [100%]",
                f"{node} ERROR [100%]",
                f"ERROR {node} - RuntimeError: cleanup failed",
                "=== 1 passed, 1 error in 0.42s ===",
            ]
        )
        full, normal = PytestReport().render(text)
        assert full == text
        assert "cleanup failed" in normal
        assert f"{node} PASSED [100%]" in normal
        assert normal.count(node) == 2
        assert f"{node} ERROR [100%]" not in normal
