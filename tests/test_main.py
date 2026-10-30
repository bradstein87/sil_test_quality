"""!
@brief Tests for running the checker as a Python module.
"""

import runpy
from pathlib import Path

import pytest

from sil_test_quality import cli


class TestModuleCommand:
    """!
    @brief Check delegation from the module entry point.
    """

    @pytest.mark.parametrize("width", [None, 0])
    def test_module_preserves_arguments_and_exit_status(
        self, monkeypatch, width
    ):
        """!
        @brief Forward module arguments and the resulting exit status.
        @param monkeypatch Pytest fixture for replacing dependencies and
        restoring them afterward.
        @param width Optional report-width override, including unframed output.
        """
        calls = []
        arguments = ["sil_test_quality", "--fix", "--verbose"]
        if width is not None:
            arguments += ["--report-width", str(width), "--wrap"]
        monkeypatch.setattr(cli.sys, "argv", arguments)
        monkeypatch.setattr(
            cli.HookEnvironment,
            "__init__",
            lambda self, root: calls.append(root),
        )
        monkeypatch.setattr(
            cli.HookEnvironment,
            "run",
            lambda self, **options: calls.append(options) or 7,
        )
        with pytest.raises(SystemExit) as result:
            runpy.run_module("sil_test_quality", run_name="__main__")
        assert result.value.code == 7
        assert calls == [
            Path.cwd(),
            {
                "fix": True,
                "verbose": True,
                "brief": False,
                "report_width": width,
                "wrap": width is not None,
            },
        ]
