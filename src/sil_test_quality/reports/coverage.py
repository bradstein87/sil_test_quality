"""!
@brief Coverage part of the Report output.
"""

from io import StringIO
from pathlib import Path
from typing import Any

from coverage import Coverage

from .. import configuration as policy


class CoverageReport:
    """!
    @brief Produce full and short coverage form tables for repo in question.
    """

    def __init__(self, root: Path) -> None:
        """!
        @brief Instantiate and set repo root for coverage inspection.
        @param root - The repo directory with source file to measure coverage.
        """
        self.root = root

    def render(self, report: dict[str, Any]) -> tuple[str, str]:
        """!
        @brief Prepares & formats each file's coverage putting worst case 1st.
        @param report - Tracks which lines of source ran during testing. Helps
                        calculate coverage for the built tables.
        @return Two tables one for verbose and one for normal output.
        """
        config = self.root / "pyproject.toml"
        measured = Coverage(
            data_file=None,
            config_file=str(config) if config.is_file() else False,
        )
        measured.get_data().add_lines(
            {
                str(self.root / name): record["executed_lines"]
                for name, record in report["files"].items()
            }
        )
        stream = StringIO()
        measured.report(
            file=stream, show_missing=True, precision=2, sort="cover"
        )
        full = stream.getvalue()
        normal, count = [], 0
        for line in full.splitlines():
            if "%" in line and not line.startswith("TOTAL"):
                count += 1
                if count > policy.NORMAL_ROWS:
                    if count == policy.NORMAL_ROWS + 1:
                        normal.append("...")
                    continue
            normal.append(line)
        return full, "\n".join(normal)
