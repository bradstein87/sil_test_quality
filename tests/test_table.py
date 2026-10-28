"""!
@brief Tests for report borders, spacing and text wrapping.
"""

from sil_test_quality.table import ReportTable


class TestReportTable:
    """!
    @brief Check aligned borders without losing report text.
    """

    def test_long_rows_wrap_without_losing_content(self):
        """!
        @brief Wrap long paths without losing any text.
        """
        table = ReportTable()
        path = "src/" + "long_path/" * 40 + "example.py:123"
        rows = list(table.render("Lint", "FAIL", [path, "", "  NLOC  CCN"]))
        assert all(len(row) == 120 for row in rows)
        assert rows[1].startswith("| Lint ")
        assert rows[1].endswith(" FAIL |")
        content = "".join(row[2:-2].rstrip() for row in rows[3:-3])
        assert content == path
        assert rows[-2].startswith("|   NLOC  CCN")

    def test_native_spacing_tabs_colors_and_wide_text(self):
        """!
        @brief Account for tabs, colors and wide characters in alignment.
        """
        table = ReportTable()
        assert list(table.rows("\x1b[31mFAIL\x1b[0m\tCCN", 20)) == [
            "FAIL    CCN"
        ]
        assert list(table.rows("\u754c" * 5, 8)) == ["\u754c" * 4, "\u754c"]
        assert table.columns("e\u0301") == 1
        rows = list(table.render("Types", "PASS", ["\u754c" * 70, "e\u0301"]))
        assert all(table.columns(row) == 120 for row in rows)

    def test_long_titles_and_brief_rows_keep_status_at_the_right(self):
        """!
        @brief Keep results aligned with long titles and empty evidence.
        """
        table = ReportTable()
        title = "Source checks " * 20
        rows = list(table.render(title, "WARNING", []))
        assert rows[1].endswith(" WARNING |")
        assert all(len(row) == 120 for row in rows)
        assert len(list(table.render("Lint", "PASS", []))) == 3
        header = list(table.render("Repository: example", "", []))
        assert header[1].strip("| ") == "Repository: example"
        assert all(len(row) == 120 for row in header)
