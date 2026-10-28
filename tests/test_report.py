"""!
@brief Tests for repo metadata and report consistency checks.
"""

import re
import sys

import pytest

from sil_test_quality.output import CheckOutput
from sil_test_quality.report import QualityReport
from sil_test_quality.source import ProjectSource


class TestQualityReport:
    """!
    @brief Check report context and detection of source changes.
    """

    @pytest.mark.parametrize("verbose", [False, True])
    def test_report_visibility_and_provenance(self, tmp_path, capsys, verbose):
        """!
        @brief Keep repo and tool context with the saved check results.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        @param verbose Full-output flag selected for this test scenario.
        """

        (tmp_path / "sample.py").write_text("VALUE = 1\n")
        report = QualityReport(ProjectSource(tmp_path))
        with CheckOutput(tmp_path, verbose, brief=not verbose) as output:
            report.begin(output)
            output.result("Example check", False)
            report.emit(output, ["sample.py:1: # noqa: F401"])
            assert output.finish() == 1
        console = capsys.readouterr().out
        evidence = (tmp_path / "artifacts/precommit.log").read_text()
        assert ("- Started (UTC):" in console) == verbose
        assert re.search(r"\| Example check +FAIL \|", evidence)
        assert re.search(r"\| Result +FAIL \|", evidence)
        assert f"- Input SHA256 before: {report.fingerprint}" in evidence
        assert "Suppression: sample.py:1: # noqa: F401" in evidence
        assert "Manual review" not in evidence
        assert "CHECKING" not in console + evidence
        assert "- Tool:" not in evidence
        assert "- Line width:" not in evidence
        assert re.search(r"\| Repository +\|", console)
        assert not list(tmp_path.rglob("*.md"))

    @pytest.mark.parametrize("name", [".venv", "venv", "custom python"])
    def test_report_uses_the_running_python_environment(
        self, tmp_path, monkeypatch, name
    ):
        """!
        @brief Report runtime paths instead of guessing from a folder name.
        @param tmp_path Temporary repo used to produce the report.
        @param monkeypatch Replace runtime paths and an unrelated shell setting.
        @param name Environment directory name that should appear in the report.
        """
        prefix = str(tmp_path / name)
        executable = str(tmp_path / name / "python")
        monkeypatch.setattr(sys, "prefix", prefix)
        monkeypatch.setattr(sys, "executable", executable)
        monkeypatch.setenv("VIRTUAL_ENV", "unrelated shell environment")
        with CheckOutput(tmp_path) as output:
            QualityReport(ProjectSource(tmp_path)).begin(output)
        evidence = "".join(
            "".join(row[2:-2].split())
            for row in output.path.read_text().splitlines()
            if row.startswith("|")
        )
        assert "Pythonenvironment:" + "".join(prefix.split()) in evidence
        assert "Pythonexecutable:" + "".join(executable.split()) in evidence
        assert "unrelated shell environment" not in output.path.read_text()

    def test_input_edits_invalidate_report_but_generated_logs_do_not(
        self, tmp_path
    ):
        """!
        @brief Invalidate changed source inputs without counting new logs.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """

        source = tmp_path / "source.py"
        source.write_text("VALUE = 1\n")
        report = QualityReport(ProjectSource(tmp_path))
        with CheckOutput(tmp_path) as output:
            output.detail("Generated output is not a source edit")
            assert report.fingerprint == report.source.fingerprint()
            source.write_text("VALUE = 2\n")
            report.emit(output, [])
            assert output.finish() == 1
        evidence = (tmp_path / "artifacts/precommit.log").read_text()
        assert "INVALIDATED" in evidence
        assert output.results["Consistency"] == "FAIL"
