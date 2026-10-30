"""!
@brief Tests for report borders, spacing and text wrapping.
"""

import pytest

from sil_test_quality.table import ReportTable


class TestReportTable:
    """!
    @brief Check aligned borders without losing report text.
    """

    @pytest.mark.parametrize("width", [20, 80, 120, 160])
    def test_long_rows_wrap_without_losing_content(self, width):
        """!
        @brief Wrap long paths without losing any text.
        @param width Requested number of report columns.
        """
        table = ReportTable(width, wrap=True)
        path = "src/" + "long_path/" * 40 + "example.py:123"
        rows = list(table.render("Lint", "FAIL", [path, "", "  NLOC  CCN"]))
        assert all(len(row) == width for row in rows)
        assert rows[1].startswith("| Lint ")
        assert rows[1].endswith(" FAIL |")
        content = "".join(row[2:-2].rstrip() for row in rows[3:-3])
        assert content == path
        assert rows[-2].startswith("|   NLOC  CCN")

    @pytest.mark.parametrize("wrap", [False, True])
    def test_zero_width_keeps_headers_and_unwrapped_evidence(self, wrap):
        """!
        @brief Keep long evidence intact when framing is disabled.
        @param wrap Wrapping flag ignored by unframed output.
        """
        table = ReportTable(0, wrap=wrap)
        text = "long/path/" * 100
        rows = list(table.render("Tests", "PASS", [text, "\n  NLOC  CCN"]))
        assert rows == ["Tests  [PASS]", text, "", "  NLOC  CCN"]
        assert list(table.render("Repository", "", [])) == ["Repository"]

    def test_native_spacing_tabs_colors_and_wide_text(self):
        """!
        @brief Account for tabs, colors and wide characters in alignment.
        """
        table = ReportTable(wrap=True)
        assert list(table.rows("\x1b[31mFAIL\x1b[0m\tCCN", 20)) == [
            "FAIL    CCN"
        ]
        assert list(table.rows("\u754c" * 5, 8)) == ["\u754c" * 4, "\u754c"]
        assert table.columns("e\u0301") == 1
        rows = list(table.render("Types", "PASS", ["\u754c" * 70, "e\u0301"]))
        assert all(table.columns(row) == 128 for row in rows)

    @pytest.mark.parametrize(
        "text,width,expected",
        [
            ("short", 5, "short"),
            ("longer", 5, "lo..."),
            ("long", 2, ".."),
            ("\u754c" * 5, 8, "\u754c\u754c..."),
            ("e\u0301abcdef", 5, "e\u0301a..."),
        ],
    )
    def test_default_clipping_marks_omitted_text(self, text, width, expected):
        """!
        @brief Clip at display columns without wrapping or splitting accents.
        @param text Evidence line to fit into the report.
        @param width Available columns, including the ellipsis.
        @param expected Complete or clipped text that fits those columns.
        """
        table = ReportTable()
        assert list(table.rows(text, width)) == [expected]
        assert table.columns(expected) <= width

    def test_long_titles_and_brief_rows_keep_status_at_the_right(self):
        """!
        @brief Keep results aligned with long titles and empty evidence.
        """
        table = ReportTable()
        title = "Source checks " * 20
        rows = list(table.render(title, "WARNING", []))
        assert "..." in rows[1] and len(rows) == 3
        assert rows[1].endswith(" WARNING |")
        assert all(len(row) == 128 for row in rows)
        assert len(list(table.render("Lint", "PASS", []))) == 3
        header = list(table.render("Repository: example", "", []))
        assert header[1].strip("| ") == "Repository: example"
        assert all(len(row) == 128 for row in header)
