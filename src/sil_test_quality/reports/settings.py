"""!
@brief Resolved lint settings and descriptions of the selected rules.
"""

import json
import re
from typing import Any

from .. import configuration as policy


class SettingsReport:
    """!
    @brief Show the resolved settings and explain the enabled lint rules.
    """

    def __init__(self) -> None:
        """!
        @brief Keep the resolved rule codes for the description lookup.
        """
        self.enabled: set[str] | None = None
        self.rules_complete = False

    def render(self, text: str) -> tuple[str, str]:
        """!
        @brief Highlight resolved line widths and the Python target version.
        @param text Output from Ruff's --show-settings command. Ruff identifies
        the first selected file whose settings it reports.
        @return Full native output and a shorter view that keeps the file and
        configuration paths. Errors are kept unchanged.
        """
        match = re.search(r"(?ms)^linter\.rules\.enabled = \[(.*?)\]", text)
        self.enabled = (
            set(re.findall(r"\(([A-Z]+\d+)\)", match[1])) if match else None
        )
        if match and match[1].strip() and not self.enabled:
            self.enabled = None
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

    def describe_rules(self, text: str) -> tuple[str, str]:
        """!
        @brief Explain each rule selected by the resolved settings.
        @param text JSON catalog from the installed Ruff's rule command.
        @return Complete descriptions and a shortened normal-mode list.
        Errors leave rules_complete false so the Settings check fails.
        """
        self.rules_complete = False
        try:
            if self.enabled is None:
                raise ValueError("Enabled rules were absent from the settings")
            catalog = {rule["code"]: rule for rule in json.loads(text)}
            rows = [
                f"- {code} ({catalog[code]['name']}): "
                f"{self.description(catalog[code])}"
                for code in sorted(self.enabled)
            ]
        except json.JSONDecodeError:
            message = text.strip() or "No rule metadata returned."
            return message, message
        except (KeyError, TypeError, ValueError) as error:
            message = f"Rule descriptions unavailable: {error}"
            return message, message
        self.rules_complete = True
        heading = f"Enabled rule descriptions ({len(rows)}):"
        rows = rows or ["- No lint rules enabled."]
        normal = rows[: policy.NORMAL_ROWS]
        if len(rows) > len(normal):
            normal.append("...")
        return "\n".join([heading, *rows]), "\n".join([heading, *normal])

    @staticmethod
    def description(rule: dict[str, Any]) -> str:
        """!
        @brief Take the short explanation from a native rule entry.
        @param rule Ruff metadata containing the rule explanation and summary.
        @return The opening purpose paragraph, or Ruff's diagnostic summary
        when that paragraph is absent.
        """
        explanation = rule.get("explanation", "")
        paragraph = explanation.partition("## What it does\n")[2]
        return (
            " ".join(paragraph.split("\n\n", 1)[0].split()) or rule["summary"]
        )
