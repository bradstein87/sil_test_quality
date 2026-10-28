"""!
@brief Borders, spacing and text wrapping for the report output.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator


class ReportTable:
    """!
    @brief Format report sections into aligned 120-column blocks.
    """

    WIDTH = 120
    ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

    @staticmethod
    def bullets(text: str) -> str:
        """!
        @brief Prepare report text as bullet points.
        @param text Evidence from CheckOutput.detail to format for the section.
        @return Text with bullets added, keeping existing indentation and
        omission marks.
        """
        return "\n".join(
            line
            if not line or line == "..." or line.startswith(("-", " ", "\t"))
            else "- " + line
            for line in text.splitlines()
        )

    @staticmethod
    def columns(text: str) -> int:
        """!
        @brief Measure the space text takes on a terminal line.
        @param text Plain text to measure, with tabs expanded and colors
        removed.
        @return Display-column count used to align borders and wrap text.
        """
        return sum(
            0
            if unicodedata.combining(char)
            else 2
            if unicodedata.east_asian_width(char) in "WF"
            else 1
            for char in text
        )

    def rows(self, text: str, width: int) -> Iterator[str]:
        """!
        @brief Wrap text to fit inside the report borders.
        @param text Header or evidence text from render to split into rows.
        @param width Available display columns inside the border. At least two.
        @return Text rows yielded in order for render to pad and surround with
        borders.
        """
        clean = self.ANSI.sub("", text).expandtabs()
        for line in clean.splitlines() or [""]:
            row, used = "", 0
            for char in line:
                size = self.columns(char)
                if used + size > width:
                    yield row
                    row, used = "", 0
                row += char
                used += size
            yield row

    def render(
        self, title: str, status: str, details: Iterable[str]
    ) -> Iterator[str]:
        """!
        @brief Build a report block with the result on the right.
        @param title Section name from the caller, shown on the left.
        @param status Result or running indicator shown on the right. May be
        empty.
        @param details Evidence strings for the block. Empty for a header-only
        view.
        @return Lines of the bordered block for CheckOutput to print or save.
        """
        width = self.WIDTH - 4
        border = "+" + "-" * (self.WIDTH - 2) + "+"
        yield border
        titles = iter(
            self.rows(title, width - (len(status) + 1 if status else 0))
        )
        first = next(titles)
        padding = width - self.columns(first) - len(status)
        yield "| " + first + " " * padding + status + " |"
        for line in titles:
            yield "| " + line + " " * (width - self.columns(line)) + " |"
        yield border
        has_details = False
        for detail in details:
            has_details = True
            for line in self.rows(detail, width):
                yield "| " + line + " " * (width - self.columns(line)) + " |"
        if has_details:
            yield border
