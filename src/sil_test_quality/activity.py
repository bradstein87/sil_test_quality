"""!
@brief Running-check indicator for the report headers.
"""

import sys
from shutil import get_terminal_size
from threading import Event, Thread

from .table import ReportTable


class CheckActivity:
    """!
    @brief Manage the animated header while a check is running.
    @details CheckOutput starts and stops the background thread. Stop it before
    printing other console output. Pipes and terminals narrower than the
    header get no animation.
    """

    def __init__(self, table: ReportTable | None = None) -> None:
        """!
        @brief Set up the console stream and stop signal.
        @param table Formatter shared with the completed report blocks.
        None uses the default report width.
        """
        self.label = ""
        self.stream = sys.stdout
        self.done = Event()
        self.thread: Thread | None = None
        self.table = table or ReportTable()

    def start(self, label: str) -> None:
        """!
        @brief Show the check name and animate its pending result.
        @param label Check name from CheckOutput, shown in the running header.
        @throws RuntimeError A previous check is still active and has not been
        stopped.
        """
        if self.label:
            raise RuntimeError("Finish the current check before starting one")
        self.label = label
        if not self.stream.isatty():
            return
        rows = self.header(".")
        columns = get_terminal_size((ReportTable.DEFAULT_WIDTH, 24)).columns
        if max(self.table.columns(row) for row in rows) > columns:
            return
        self.done.clear()
        self.stream.write("\n".join(rows))
        self.stream.flush()
        self.thread = Thread(target=self.animate, daemon=True)
        self.thread.start()

    def header(self, status: str) -> list[str]:
        """!
        @brief Format the temporary header using the report's selected width.
        @param status Dots showing activity in place of the final result.
        @return Border and title rows, or just the title in unframed mode.
        """
        rows = list(self.table.render(self.label, status, []))
        return rows[:2] if self.table.width else rows

    def animate(self) -> None:
        """!
        @brief Cycle the header dots until the check finishes.
        @details Runs in the background thread. The dots show activity, not how
        much of the check is complete.
        """
        count = 1
        while not self.done.wait(0.5):
            count = count % 3 + 1
            header = self.header("." * count)[-1]
            self.stream.write("\r" + header)
            self.stream.flush()

    def stop(self, *, discard: bool = False) -> bool:
        """!
        @brief Stop the animation before printing the check result.
        @param discard True to erase the temporary header when its completed
        block will be printed later.
        @return True when CheckOutput should finish the existing header in
        place, or false when it should print a complete block.
        """
        active = self.thread is not None
        self.done.set()
        if self.thread is not None:
            self.thread.join()
        self.thread = None
        self.label = ""
        if active and discard:
            self.stream.write("\r\033[2K")
            if self.table.width:
                self.stream.write("\033[1A\033[2K")
            self.stream.write("\r")
            self.stream.flush()
        return active
