"""!
@brief Full and shortened views of Ruff's resolved settings.
"""

from .. import configuration as policy


class SettingsReport:
    """!
    @brief Keep native settings output with a short view of the main limits.
    """

    def render(self, text: str) -> tuple[str, str]:
        """!
        @brief Highlight resolved line widths and the Python target version.
        @param text Output from Ruff's --show-settings command. Ruff identifies
        the first selected file whose settings it reports.
        @return Full native output and a shorter view that keeps the file and
        configuration paths. Errors are kept unchanged.
        """
        lines = text.splitlines()
        context = [
            line
            for line in lines
            if line.startswith(("Resolved settings for:", "Settings path:"))
        ]
        values = [
            line
            for line in lines
            if line.startswith(
                (
                    "linter.line_length =",
                    "formatter.line_width =",
                    "linter.target_version =",
                )
            )
        ]
        if not values:
            return text, text
        normal = context + values[: policy.NORMAL_ROWS]
        if len(lines) > len(normal):
            normal.append("...")
        return text, "\n".join(normal)
