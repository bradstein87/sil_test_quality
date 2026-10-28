"""!
@brief Tests for full and shortened resolved settings reports.
"""

import json

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

    def test_rule_names_and_descriptions_come_from_metadata(self):
        """!
        @brief Use tool metadata and keep every enabled rule in the full view.
        """
        report = SettingsReport()
        report.render(
            "linter.rules.enabled = [\n"
            "    rule (E402), rule (E401), rule (E501), rule (B006),\n]\n"
            "linter.rules.should_fix = [rule (F401)]\n"
        )
        catalog = [
            {
                "code": code,
                "name": f"name-from-tool-{code}",
                "explanation": (
                    f"## What it does\nPurpose for {code}\nfrom the tool.\n\n"
                    "## Why is this bad?\nLonger background."
                ),
            }
            for code in ("E501", "E402", "E401", "B006", "F401")
        ]
        full, normal = report.describe_rules(json.dumps(catalog))
        for code in ("B006", "E401", "E402", "E501"):
            assert (
                f"- {code} (name-from-tool-{code}): "
                f"Purpose for {code} from the tool."
            ) in full
        assert full.index("B006") < full.index("E401") < full.index("E402")
        assert "F401" not in full and "Longer background" not in full
        assert "E501" not in normal and normal.endswith("...")
        assert report.rules_complete

    def test_summary_is_used_when_the_purpose_paragraph_is_absent(self):
        """!
        @brief Keep rules readable when Ruff provides only a summary.
        """
        report = SettingsReport()
        report.render("linter.rules.enabled = [rule (E401)]")
        catalog = [{"code": "E401", "name": "native", "summary": "Summary."}]
        full, normal = report.describe_rules(json.dumps(catalog))
        assert "- E401 (native): Summary." in full
        assert full == normal
        assert report.rules_complete

    @pytest.mark.parametrize("text", ["ruff failed", ""])
    def test_metadata_errors_are_reported(self, text):
        """!
        @brief Keep command failures visible instead of claiming descriptions.
        @param text Invalid or missing JSON from the rule metadata command.
        """
        report = SettingsReport()
        report.render("linter.rules.enabled = [rule (E401)]")
        full, normal = report.describe_rules(text)
        assert full == normal == (text or "No rule metadata returned.")
        assert not report.rules_complete

    @pytest.mark.parametrize("metadata", ["[]", "null", '[{"code":"E401"}]'])
    def test_incomplete_metadata_is_a_failure(self, metadata):
        """!
        @brief Fail the report when selected rules cannot be described.
        @param metadata Catalog with a missing rule, name or description.
        """
        report = SettingsReport()
        report.render("linter.rules.enabled = [rule (E401)]")
        full, normal = report.describe_rules(metadata)
        assert full == normal
        assert full.startswith("Rule descriptions unavailable:")
        assert not report.rules_complete

    @pytest.mark.parametrize(
        "settings", ["No settings returned", "linter.rules.enabled = [unknown]"]
    )
    def test_unreadable_settings_are_not_an_empty_selection(self, settings):
        """!
        @brief Fail when the enabled-rule list cannot be read.
        @param settings Missing or unrecognized resolved settings output.
        """
        report = SettingsReport()
        report.render(settings)
        full, normal = report.describe_rules("[]")
        assert "Enabled rules were absent" in full
        assert full == normal
        assert not report.rules_complete

    def test_no_enabled_rules_is_a_valid_selection(self):
        """!
        @brief Allow a resolved configuration that disables every lint rule.
        """
        report = SettingsReport()
        report.render("linter.rules.enabled = []")
        full, normal = report.describe_rules("[]")
        assert "No lint rules enabled." in full
        assert full == normal
        assert report.rules_complete
