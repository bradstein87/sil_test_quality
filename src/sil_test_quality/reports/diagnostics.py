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
        leading, blocks, trailing = self.records(text)
        if not blocks:
            return text, self._unstructured(text)
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
        normal = leading + [
            line for _, block in blocks[: policy.NORMAL_ROWS] for line in block
        ]
        if len(blocks) > policy.NORMAL_ROWS:
            normal.append("...")
        normal.extend(trailing)
        return text, "\n".join(normal)

    @staticmethod
    def _unstructured(text: str) -> str:
        """!
        @brief Shorten plain output while keeping its opening and final lines.
        @param text Tool output with no recognized file diagnostics.
        @return Unchanged short output or boundary lines surrounding three
        prioritized middle lines and an omission marker.
        """
        lines = text.strip().splitlines()
        if len(lines) <= policy.NORMAL_ROWS + 2:
            return text
        middle = sorted(
            lines[1:-1],
            key=lambda line: not bool(
                re.search(r"error|failed|exception", line, re.I)
            ),
        )
        return "\n".join(
            [lines[0], *middle[: policy.NORMAL_ROWS], "...", lines[-1]]
        )

    def records(
        self, text: str
    ) -> tuple[list[str], list[tuple[str, list[str]]], list[str]]:
        """!
        @brief Pair diagnostic issues with corresponding explainations.
        @param text Outputs in Render: file paths, summaries, explainations.
        @return Opening context, grouped file diagnostics, and closing messages.
        """
        blocks: list[tuple[str, list[str]]] = []
        leading: list[str] = []
        trailing: list[str] = []
        for line in text.splitlines():
            match = self.LOCATION.match(line)
            if match:
                blocks.append((match[1], [line]))
            elif line.startswith("Would reformat:"):
                blocks.append((line.split(":", 1)[1].strip(), [line]))
            elif blocks and (line.startswith((" ", "help:")) or not line):
                blocks[-1][1].append(line)
            else:
                (trailing if blocks else leading).append(line)
        return leading, blocks, trailing
