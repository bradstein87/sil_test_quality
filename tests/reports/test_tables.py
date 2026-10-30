"""!
@brief Tests for sorted and shortened Lizard report tables.
"""

from sil_test_quality.reports.tables import LizardReport


class TestLizardReport:
    """!
    @brief Check full and normal complexity and length views.
    """

    def test_each_table_keeps_three_worst_rows(self):
        """!
        @brief Keep the three highest-complexity rows in each normal table.
        """
        functions = [
            f"  1 {score} 9 0 7 f{score}@1@src/a.py" for score in [2, 18, 4, 11]
        ]
        files = [
            f"  1 7.0 {score}.0 9.0 1 src/f{score}.py"
            for score in [2, 18, 4, 11]
        ]
        total = " 34 6.0 8.0 10.0 4 1 0.25 0.25"
        text = "\n".join(
            [
                "NLOC CCN token PARAM length location",
                *functions,
                "4 file analyzed.",
                "NLOC Avg.NLOC AvgCCN Avg.token function_cnt file",
                *files,
                "Warnings (cyclomatic_complexity > 20 or length > 60)",
                "NLOC CCN token PARAM length location",
                *functions,
                "Total nloc Avg.NLOC AvgCCN Avg.token "
                "Fun Cnt Warning cnt Fun Rt nloc Rt",
                total,
            ]
        )
        full, normal = LizardReport().render(text)
        assert full.count("f2@") == 2
        assert "f2@" not in normal and "src/f2.py" not in normal
        assert full.index("f18@") < full.index("f11@") < full.index("f4@")
        assert full.index("src/f18.py") < full.index("src/f11.py")
        assert normal.count("...") == 3
        assert normal.endswith(total) and full.endswith(total)
        assert "Warnings (" in normal and "4 file analyzed." in normal

    def test_short_report_needs_no_truncation(self):
        """!
        @brief Keep short reports complete in both views.
        """
        text = (
            "NLOC CCN token PARAM length location\n"
            "0 file analyzed.\nNo warnings."
        )
        report = LizardReport()
        assert report.render(text) == (text, text)
        assert report.lengths() == ("- No functions measured.",) * 2

    def test_length_report_is_longest_first_without_duplicate_warnings(self):
        """!
        @brief List longest functions first without repeated warning rows.
        """
        header = "NLOC CCN token PARAM length location"
        rows = [
            f"1 2 9 0 {length} f{length}@1@sample.py"
            for length in [61, 160, 60, 80, 120]
        ]
        text = "\n".join(
            [header, *rows, "1 file analyzed.", "Warnings", header, *rows]
        )
        report = LizardReport()
        report.render(text)
        full, normal = report.lengths()
        assert full.count("f160@") == 1
        assert "f60@" in full and "f60@" not in normal
        assert full.index("f160@") < full.index("f120@") < full.index("f80@")
        assert "f61@" in full and "f61@" not in normal
        assert normal.splitlines()[-1] == "..."
        assert full.startswith(header) and normal.startswith(header)
