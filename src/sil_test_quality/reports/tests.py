"""!
@brief Unit test - PyTest part of the Report output.
"""

import re

from .. import configuration as policy
from .diagnostics import DiagnosticReport


class TestReport:
    """!
    @brief PyTest summarized output that keeps failure and execution outputs
    """

    PRIORITY = {
        "ERROR": 0,
        "FAILED": 1,
        "XPASS": 2,
        "SKIPPED": 3,
        "XFAIL": 4,
        "PASSED": 5,
    }
    RESULT = re.compile(
        r"^(\S.*?::.+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b"
    )
    SUMMARY = re.compile(r"^(ERROR|FAILED|XPASS) (.+)")

    def render(self, text: str) -> tuple[str, str]:
        """!
        @brief Prepare the most critical PyTest results & sessions totals
        @param text PyTest console output, outcomes & totals to pick priorities
        @return Output for verbose and normal mode with top results for normal
        """
        lines = text.splitlines()
        rows, summaries = {}, []
        context, totals = [], []
        for line in lines:
            result = self.RESULT.match(line)
            summary = self.SUMMARY.match(line)
            if result:
                rows[result[1]] = (self.PRIORITY[result[2]], line)
            elif summary:
                summaries.append((self.PRIORITY[summary[1]], line))
            elif line.startswith(
                (
                    "platform ",
                    "rootdir:",
                    "configfile:",
                    "plugins:",
                    "collected ",
                )
            ):
                context.append(line)
            elif re.match(r"=+ .* in [\d.]+s", line):
                totals.append(line)
        # Short summaries add the exception/reason missing from progress rows.
        for priority, line in summaries:
            node = line.split(" ", 1)[1].split(" - ", 1)[0]
            rows[node] = (priority, line)
        ranked = sorted(rows.values(), key=lambda row: row[0])
        if not ranked:
            return DiagnosticReport().render(text)
        normal = (
            totals
            + context
            + [line for _, line in ranked[: policy.NORMAL_ROWS]]
        )
        if len(ranked) > policy.NORMAL_ROWS:
            normal.append("...")
        return text, "\n".join(normal)
