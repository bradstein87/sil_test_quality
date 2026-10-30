"""!
@brief Repo settings and shared limits for the precommit checks.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

from .table import ReportTable

# Limits used by checks and their report descriptions.
MAX_FILE_LINES = 500
MAX_LINE_COLUMNS = 80
MAX_COMPLEXITY = 20
FUNCTION_REVIEW_LINES = 60
MIN_FILE_COVERAGE = 90

# Maximum entries shown per table or finding list in normal mode.
NORMAL_ROWS = 3


class CheckSettings:
    """!
    @brief Read and validate settings for the repo being checked.
    """

    def __init__(self, root: Path) -> None:
        """!
        @brief Load checker settings and fill in defaults.
        @param root Repo whose pyproject.toml supplies version, report and
        coverage settings.
        @throws ValueError A setting has an unsupported name, type, version
        format or path.
        """
        options = self.read_options(root)
        self.version = options.get("version")
        self.coverage_omit = options.get("coverage-omit", [])
        self.version_file = options.get("version-file", "")
        self.report_width = options.get(
            "report-width", ReportTable.DEFAULT_WIDTH
        )
        ReportTable.validate_width(self.report_width)
        if not isinstance(self.version, str) or not re.fullmatch(
            r"\d+\.\d+\.\d+", self.version
        ):
            raise ValueError("sil-test-quality.version must be an exact X.Y.Z")
        self.validate_paths()

    @staticmethod
    def read_options(root: Path) -> dict[str, Any]:
        """!
        @brief Read the repo's checker settings.
        @param root Repo directory used to locate the configuration file.
        @return Supported settings from the tool.sil-test-quality table.
        @throws ValueError The checker section is not a table or contains
        unsupported keys.
        """
        path = root / "pyproject.toml"
        data = tomllib.loads(path.read_text()) if path.exists() else {}
        options = data.get("tool", {}).get("sil-test-quality", {})
        if not isinstance(options, dict):
            raise ValueError("tool.sil-test-quality must be a table")
        allowed = {"version", "coverage-omit", "version-file", "report-width"}
        unknown = options.keys() - allowed
        if unknown:
            raise ValueError(
                f"Unknown sil-test-quality settings: {sorted(unknown)}"
            )
        return options

    def validate_paths(self) -> None:
        """!
        @brief Check that configured paths stay within the repo.
        @details Checks path types and rejects absolute paths or parent
        traversal. Coverage omissions may be patterns. Files need not exist yet.
        @throws ValueError Path settings have invalid types or refer outside the
        repository.
        """
        if not isinstance(self.coverage_omit, list) or not all(
            isinstance(value, str) and value for value in self.coverage_omit
        ):
            raise ValueError(
                "sil-test-quality.coverage-omit must be a string list"
            )
        if not isinstance(self.version_file, str):
            raise ValueError(
                "sil-test-quality.version-file must be a relative path"
            )
        for value in [*self.coverage_omit, self.version_file]:
            if Path(value).is_absolute() or ".." in Path(value).parts:
                raise ValueError(
                    "sil-test-quality paths must stay in the repository"
                )
