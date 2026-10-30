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
        @return Full output and a normal view with session context, up to three
        prioritized native results, and the final totals.
        """
        lines = text.splitlines()
        rows: dict[tuple[str, str], str] = {}
        summaries = []
        context = []
        totals = []
        for line in lines:
            result = self.RESULT.match(line)
            summary = self.SUMMARY.match(line)
            if result:
                rows[result[1], result[2]] = line
            elif summary:
                summaries.append((summary[1], line))
            elif re.match(r"=+ .* in [\d.]+s", line):
                totals.append(line)
            elif line.startswith(
                (
                    "rootdir:",
                    "configfile:",
                    "testpaths:",
                    "collected ",
                    "collecting ",
                )
            ):
                context.append(line)
        # Short summaries add the exception/reason missing from progress rows.
        for status, line in summaries:
            message = line.split(" ", 1)[1]
            node = message.split(" - ", 1)[0]
            for candidate, outcome in rows:
                if outcome == status and message.startswith(candidate + " - "):
                    node = candidate
                    break
            rows[node, status] = line
        if not rows:
            return DiagnosticReport().render(text)
        ranked = sorted(
            (
                (self.PRIORITY[status], line)
                for (_, status), line in rows.items()
            ),
            key=lambda row: row[0],
        )
        normal = context + [line for _, line in ranked[: policy.NORMAL_ROWS]]
        if len(ranked) > policy.NORMAL_ROWS:
            normal.append("...")
        normal.extend(totals)
        return text, "\n".join(normal)
