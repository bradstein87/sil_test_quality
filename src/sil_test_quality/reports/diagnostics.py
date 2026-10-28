"""!
@brief Error message management and trucation part of the Report output.
"""

import re
from collections import Counter

from .. import configuration as policy


class DiagnosticReport:
    """!
    @brief Prepare errors output of tools for the report, shorten/collapse
    """

    LOCATION = re.compile(r"^(.*?\.py):\d+(?::\d+)?:")

    def render(self, text: str) -> tuple[str, str]:
        """!
        @brief Prepare tool/checker messages, prioritizing issues for normal
               output.
        @param text Captured tool/checker output used to sort & select issues.
        @return verbose output, logging, & normal with prioritized findings.
        """
        blocks, trailing = self.records(text)
        if not blocks:
            lines = text.splitlines()
            ranked = sorted(
                lines,
                key=lambda line: not bool(
                    re.search(r"error|failed|exception", line, re.I)
                ),
            )
            preview = (
                "\n".join([*ranked[: policy.NORMAL_ROWS], "..."])
                if len(lines) > policy.NORMAL_ROWS
                else text
            )
            return text, preview
        counts = Counter(name for name, _ in blocks)
        blocks.sort(
            key=lambda item: (
                not bool(
                    re.search(
                        r"invalid-syntax|SyntaxError|\bE9\d+|\bF82\d",
                        item[1][0],
                    )
                ),
                -counts[item[0]],
                item[0],
            )
        )
        normal = [
            line for _, block in blocks[: policy.NORMAL_ROWS] for line in block
        ]
        if len(blocks) > policy.NORMAL_ROWS:
            normal.append("...")
        normal.extend(trailing)
        return text, "\n".join(normal)

    def records(
        self, text: str
    ) -> tuple[list[tuple[str, list[str]]], list[str]]:
        """!
        @brief Pair diagnostic issues with corresponding explainations.
        @param text Outputs in Render: file paths, summaries, explainations.
        @return two lists - pairs to rank in render & upgrouped lines - totals.
        """
        blocks: list[tuple[str, list[str]]] = []
        trailing = []
        for line in text.splitlines():
            match = self.LOCATION.match(line)
            if match:
                blocks.append((match[1], [line]))
            elif line.startswith("Would reformat:"):
                blocks.append((line.split(":", 1)[1].strip(), [line]))
            elif blocks and (line.startswith((" ", "help:")) or not line):
                blocks[-1][1].append(line)
            else:
                trailing.append(line)
        return blocks, trailing
