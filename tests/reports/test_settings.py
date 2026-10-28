"""!
@brief Tests for full and shortened resolved settings reports.
"""

import pytest

from sil_test_quality import configuration as policy
from sil_test_quality.reports.settings import SettingsReport


class TestSettingsReport:
    """!
    @brief Preserve native settings and show useful values in normal mode.
    """

    def test_resolved_values_and_shared_row_limit(self, monkeypatch):
        """!
        @brief Keep file context and use the shared limit for setting rows.
        @param monkeypatch Reduce the normal-mode row limit for this test.
        """
        monkeypatch.setattr(policy, "NORMAL_ROWS", 1)
        text = (
            'Resolved settings for: "src/example.py"\n'
            'Settings path: "pyproject.toml"\n'
            'cache_dir = "cache"\n'
            "linter.line_length = 100\n"
            "formatter.line_width = 100\n"
            "linter.target_version = Py312\n"
        )
        full, normal = SettingsReport().render(text)
        assert full == text
        assert 'Resolved settings for: "src/example.py"' in normal
        assert 'Settings path: "pyproject.toml"' in normal
        assert "linter.line_length = 100" in normal
        assert "formatter.line_width" not in normal
        assert "cache_dir" not in normal and normal.endswith("...")

    @pytest.mark.parametrize("text", ["ruff failed", "linter.line_length = 80"])
    def test_short_settings_or_errors_are_kept(self, text):
        """!
        @brief Keep short settings reports and failures complete.
        @param text Native output with one setting or a command failure.
        """
        assert SettingsReport().render(text) == (text, text)
