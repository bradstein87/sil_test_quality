"""!
@brief Tests for diagnostic grouping and report priorities.
"""

from sil_test_quality.reports.diagnostics import DiagnosticReport


class TestDiagnosticReport:
    """!
    @brief Check shortened messages keep useful context.
    """

    def test_rank_and_keep_context(self):
        """!
        @brief Prioritize issues without separating their explanations.
        """
        text = "\n".join(
            [
                "src/one.py:1: error: single type error",
                "src/many.py:1: error: first type error",
                "    source context",
                "src/many.py:2: error: second type error",
                "help: repair this",
                "src/many.py:3: error: third type error",
                "src/syntax.py:1:1: invalid-syntax: parse failed",
                "Found 5 errors.",
            ]
        )
        full, normal = DiagnosticReport().render(text)
        assert full == text
        assert normal.startswith("src/syntax.py")
        assert "src/one.py" not in normal and "third type" not in normal
        assert "source context" in normal and "help: repair" in normal
        assert "Found 5 errors." in normal
        assert "..." in normal

    def test_formatting_files_and_unstructured_errors(self):
        """!
        @brief Handle formatter output and messages without locations.
        """
        text = "\n".join(f"Would reformat: src/{name}.py" for name in "abcd")
        full, normal = DiagnosticReport().render(text)
        assert full == text and "src/d.py" not in normal
        full, normal = DiagnosticReport().render(
            "one\ntwo\nthree\nfour\nERROR tool failed"
        )
        assert full.endswith("ERROR tool failed")
        assert normal.startswith("ERROR tool failed")
        assert "..." in normal
        assert DiagnosticReport().render("All checks passed!") == (
            "All checks passed!",
            "All checks passed!",
        )
