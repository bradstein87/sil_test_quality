"""!
@brief Tests for shared tool rules and repository additions.
"""

import subprocess
import sys
import tomllib

import pytest

from sil_test_quality.policy import ToolPolicy


class TestToolPolicy:
    """!
    @brief Keep the baseline active when consumers add configuration.
    """

    def test_default_policy_is_packaged_and_written(self, checked_project):
        """!
        @brief Write both native configs when the consumer supplies no rules.
        @param checked_project Minimal repository without tool configuration.
        """
        policy = ToolPolicy(checked_project)
        assert policy.baseline.is_file()
        assert policy.additions == {}
        for tool, flag in (("ruff", "--config"), ("mypy", "--config-file")):
            arguments = policy.arguments(tool)
            assert arguments == [flag, str(policy.directory / f"{tool}.toml")]
        ruff = tomllib.loads((policy.directory / "ruff.toml").read_text())
        mypy = tomllib.loads((policy.directory / "mypy.toml").read_text())
        assert "PLC0415" in ruff["lint"]["select"]
        assert ruff["line-length"] == 80
        assert mypy["tool"]["mypy"]["disallow_untyped_defs"] is True

    def test_additions_preserve_the_baseline(self, checked_project):
        """!
        @brief Merge consumer rules while keeping every shared rule active.
        @param checked_project Minimal repo receiving additional tool settings.
        """
        with (checked_project / "pyproject.toml").open("a") as stream:
            stream.write(
                '\n[tool.ruff]\ntarget-version = "py312"\nline-length = 72\n'
                '[tool.ruff.lint]\nselect = ["UP"]\nextend-select = ["C4"]\n'
                '[tool.ruff.lint.isort]\nknown-first-party = ["example"]\n'
                "[tool.ruff.lint.flake8-tidy-imports.banned-api]\n"
                '"os.system" = {msg = "Use subprocess."}\n'
                '[tool.mypy]\npython_version = "3.12"\n'
                "disallow_any_generics = true\n"
                'enable_error_code = ["truthy-bool"]\n'
                '[[tool.mypy.overrides]]\nmodule = "untyped_vendor"\n'
                "ignore_missing_imports = true\n"
            )
        policy = ToolPolicy(checked_project)
        ruff = policy.settings["ruff"]
        assert ruff["line-length"] == 72
        assert ruff["target-version"] == "py312"
        assert {"UP", "PLC0415", "E501"} <= set(ruff["lint"]["select"])
        bans = ruff["lint"]["flake8-tidy-imports"]["banned-api"]
        assert "os.system" in bans and "_pytest" in bans
        assert policy.settings["mypy"]["disallow_untyped_defs"] is True
        assert policy.settings["mypy"]["overrides"][0]["ignore_missing_imports"]

    @pytest.mark.parametrize(
        "settings, option",
        [
            ("[tool.ruff]\nline-length = 120", "ruff.line-length"),
            ("[tool.ruff]\nline-length = true", "ruff.line-length"),
            ('[tool.ruff]\nextend = "other.toml"', "ruff.extend"),
            ('[tool.ruff.lint]\nignore = ["PLC0415"]', "ruff.lint.ignore"),
            ("[tool.ruff.lint]\npreview = false", "ruff.lint.preview"),
            ('[tool.ruff.lint]\nselect = "ALL"', "list of strings"),
            ('[tool.ruff]\nlint = "invalid"', "must be a table"),
            ('[tool.ruff.lint.per-file-ignores]\n"*" = ["F"]', "per-file"),
            ('[tool.ruff]\nexclude = ["src"]', "ruff.exclude"),
            ("[tool.mypy]\ndisallow_untyped_defs = false", "untyped_defs"),
            ("[tool.mypy]\nignore_errors = true", "ignore_errors"),
            ('[tool.mypy]\ndisable_error_code = ["assignment"]', "disable"),
            ("[tool.mypy]\ndisallow_any_generics = false", "any_generics"),
            ('[tool.mypy]\noverrides = "invalid"', "list of tables"),
            (
                "[[tool.mypy.overrides]]\nignore_errors = true",
                "name its modules",
            ),
            ("[[tool.mypy.overrides]]\nmodule = 3", "nonempty names"),
            (
                '[[tool.mypy.overrides]]\nmodule = "*"\n'
                "ignore_missing_imports = true",
                "exact modules",
            ),
            (
                '[[tool.mypy.overrides]]\nmodule = "example"\n'
                "ignore_errors = true",
                "ignore_errors",
            ),
        ],
    )
    def test_settings_cannot_weaken_checks(
        self, checked_project, settings, option
    ):
        """!
        @brief Reject options that replace or suppress baseline checks.
        @param checked_project Repository receiving the conflicting setting.
        @param settings TOML configuration that should be rejected.
        @param option Setting name or explanation expected in the error.
        """
        with (checked_project / "pyproject.toml").open("a") as stream:
            stream.write("\n" + settings + "\n")
        with pytest.raises(ValueError, match=option):
            ToolPolicy(checked_project)

    def test_existing_baseline_values_are_accepted(self, checked_project):
        """!
        @brief Permit matching settings during migration without duplicates.
        @param checked_project Repo receiving a copy of the baseline settings.
        """
        baseline = ToolPolicy(checked_project).baseline.read_text()
        with (checked_project / "pyproject.toml").open("a") as stream:
            stream.write("\n" + baseline)
        assert (
            ToolPolicy(checked_project).settings
            == tomllib.loads(baseline)["tool"]
        )

    @pytest.mark.parametrize("name", ["ruff.toml", ".ruff.toml", "mypy.ini"])
    def test_separate_configs_are_reported(self, checked_project, name):
        """!
        @brief Report standalone configs instead of silently ignoring them.
        @param checked_project Repo containing a standalone tool config.
        @param name Filename used by the tool's normal discovery rules.
        """
        (checked_project / name).touch()
        with pytest.raises(ValueError, match="pyproject.toml"):
            ToolPolicy(checked_project)

    def test_mypy_allows_stricter_module_checks(self, checked_project):
        """!
        @brief Permit stricter checks for named modules.
        @param checked_project Repo receiving module-specific checks.
        """
        with (checked_project / "pyproject.toml").open("a") as stream:
            stream.write(
                '\n[[tool.mypy.overrides]]\nmodule = ["example.*"]\n'
                "disallow_any_generics = true\n"
            )
        overrides = ToolPolicy(checked_project).settings["mypy"]["overrides"]
        assert overrides[0]["disallow_any_generics"] is True

    def test_native_tools_enforce_baseline_and_additions(self, checked_project):
        """!
        @brief Exercise the generated configs with real Ruff and mypy calls.
        @param checked_project Repo containing baseline and additional faults.
        """
        with (checked_project / "pyproject.toml").open("a") as stream:
            stream.write(
                '\n[tool.ruff.lint]\nextend-select = ["T201"]\n'
                "[tool.mypy]\ndisallow_any_generics = true\n"
            )
        path = checked_project / "src/example.py"
        path.write_text(
            "def read(value: list):\n"
            "    import sys\n"
            "    print(sys.version)\n"
            "    return value\n"
        )
        policy = ToolPolicy(checked_project)
        for tool, operation, errors in (
            ("ruff", ["check"], ("PLC0415", "T201")),
            ("mypy", [], ("no-untyped-def", "type-arg")),
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    tool,
                    *operation,
                    *policy.arguments(tool),
                    str(path),
                ],
                cwd=checked_project,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 1, result.stdout + result.stderr
            assert all(error in result.stdout for error in errors)

    def test_nested_configs_cannot_disable_baseline(self, checked_project):
        """!
        @brief Keep the explicit config active below nested tool configs.
        @param checked_project Repo with a nested Ruff file disabling all rules.
        """
        source = checked_project / "src"
        (source / "ruff.toml").write_text("[lint]\nselect = []\n")
        path = source / "example.py"
        path.write_text("def read():\n    import os\n    return os.name\n")
        policy = ToolPolicy(checked_project)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                *policy.arguments("ruff"),
                str(path),
            ],
            cwd=checked_project,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert "PLC0415" in result.stdout
