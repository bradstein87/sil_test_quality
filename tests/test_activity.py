"""!
@brief Tests for running-header animation and static output.
"""

import io
import os
from unittest.mock import Mock

import pytest

from sil_test_quality.activity import CheckActivity
from sil_test_quality.output import CheckOutput


class TestCheckActivity:
    """!
    @brief Check header updates and animation cleanup.
    """

    @pytest.mark.parametrize("width", [0, 80, 160])
    def test_deferred_headers_match_the_selected_width(
        self, tmp_path, monkeypatch, width
    ):
        """!
        @brief Clear temporary headers before printing reordered blocks.
        @param tmp_path Directory for the saved report.
        @param monkeypatch Supply a wide terminal to exercise live headers.
        @param width Selected framed or unframed report layout.
        """
        stream = io.StringIO()
        monkeypatch.setattr(stream, "isatty", lambda: True)
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr(
            "sil_test_quality.activity.get_terminal_size",
            lambda _: os.terminal_size((200, 24)),
        )
        with CheckOutput(tmp_path, width=width) as output:
            output.defer("Coverage", "Tests")
            for label in ("Tests", "Coverage"):
                output.start(label)
                output.detail("Measured evidence")
                output.result(label, True)
            assert output.finish() == 0
        console = stream.getvalue()
        assert console.count("\033[1A") == (2 if width else 0)
        assert console.rfind("Coverage") < console.rfind("Tests")
        assert console.rfind("Tests") < console.rfind("Result")
        log = output.path.read_text()
        assert "Measured evidence" in log and "\033" not in log
        if width:
            assert all(len(row) in (0, width) for row in log.splitlines())
        else:
            assert "Tests  [PASS]" in log and "+---" not in log

    @pytest.mark.parametrize("discard", [False, True])
    def test_frames_cycle_in_place_and_stop_between_sections(
        self, monkeypatch, discard
    ):
        """!
        @brief Cycle dots in place and reset before the next check.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param discard Erase the temporary header for a held report block.
        """
        stream = io.StringIO()
        monkeypatch.setattr(stream, "isatty", lambda: True)
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr(
            "sil_test_quality.activity.get_terminal_size",
            lambda _: os.terminal_size((128, 24)),
        )
        activity = CheckActivity()
        monkeypatch.setattr(
            activity.done, "wait", Mock(side_effect=[False, False, False, True])
        )
        activity.start("Tests")
        thread = activity.thread
        try:
            with pytest.raises(RuntimeError, match="Finish the current"):
                activity.start("Coverage")
            thread.join(timeout=2)
            assert not thread.is_alive()
            frames = stream.getvalue().split("\r")
            assert frames[0].splitlines()[1].endswith(" . |")
            assert [frame.rsplit(" ", 2)[1] for frame in frames[1:]] == [
                "..",
                "...",
                ".",
            ]
            assert all(len(frame) == 128 for frame in frames[1:])
        finally:
            assert activity.stop(discard=discard)
        assert ("\033[1A" in stream.getvalue()) == discard
        assert activity.thread is None
        assert activity.label == ""
        assert not activity.stop()
        monkeypatch.setattr(activity.done, "wait", Mock(return_value=True))
        activity.start("Coverage")
        assert activity.stop()
        assert stream.getvalue().split("\n")[-1].endswith(" . |")

    @pytest.mark.parametrize("terminal,width", [(False, 120), (True, 80)])
    def test_redirected_or_narrow_output_remains_static(
        self, monkeypatch, terminal, width
    ):
        """!
        @brief Skip animation in redirected output or narrow terminals.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param terminal Whether the fake output stream reports itself as a
        terminal.
        @param width Terminal column count used to check animation availability.
        """
        stream = io.StringIO()
        monkeypatch.setattr(stream, "isatty", lambda: terminal)
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr(
            "sil_test_quality.activity.get_terminal_size",
            lambda _: os.terminal_size((width, 24)),
        )
        activity = CheckActivity()
        activity.start("Tests")
        assert activity.label == "Tests"
        assert stream.getvalue() == ""
        assert activity.thread is None
        assert not activity.stop()
