"""!
@brief Complexity and Length Lizard measurements for the report output.
"""

import re

from .. import configuration as policy


class LizardReport:
    """!
    @brief Prepare tables for complexity and function length in specific views.
    """

    ROW = re.compile(r"^\s*\d+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+\S")

    def __init__(self) -> None:
        """!
        @brief Prepare an empty function-table record.
        """
        self.function_table = ""

    def render(self, text: str) -> tuple[str, str]:
        """!
        @brief Prepare Lizard complexity tables ordered by CCN
        @param text Lizard output - function and file measurements
        @return two strings of sorted table rows for verbose & normal output
        """
        self.function_table = text.split("file analyzed.", 1)[0]
        lines = text.splitlines()
        full: list[str] = []
        normal: list[str] = []
        index, column = 0, None
        while index < len(lines):
            line = lines[index]
            if line.startswith("===") and full and full[-1]:
                full.append("")
                normal.append("")
            if line.lstrip().startswith("NLOC"):
                column = 2 if "AvgCCN" in line else 1
            elif line.startswith("Total nloc"):
                column = None
            if column is None or not self.ROW.match(line):
                full.append(line)
                normal.append(line)
                index += 1
                continue
            rows = []
            while index < len(lines) and self.ROW.match(lines[index]):
                rows.append(lines[index])
                index += 1
            rows.sort(key=lambda row: float(row.split()[column]), reverse=True)
            full.extend(rows)
            normal.extend(rows[: policy.NORMAL_ROWS])
            if len(rows) > policy.NORMAL_ROWS:
                normal.append("...")
        return "\n".join(full), "\n".join(normal)

    def lengths(self) -> tuple[str, str]:
        """!
        @brief List functions by physical length, longest first.
        @return Full and shortened native tables, or a notice when no functions
        were measured. Normal mode keeps the three longest functions.
        """
        lines = self.function_table.splitlines()
        rows = [line for line in lines if self.ROW.match(line)]
        if not rows:
            return ("- No functions measured.",) * 2
        rows.sort(key=lambda row: int(row.split()[4]), reverse=True)
        header = next(
            line for line in lines if line.lstrip().startswith("NLOC")
        )
        heading = [header, "-" * len(header)]
        full = "\n".join([*heading, *rows])
        normal = "\n".join(
            [
                *heading,
                *rows[: policy.NORMAL_ROWS],
                *(["..."] if len(rows) > policy.NORMAL_ROWS else []),
            ]
        )
        return full, normal
