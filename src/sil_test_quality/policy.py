"""!
@brief Combine shared tool rules with repository additions.
"""

import tomllib
from pathlib import Path
from typing import Any

import tomli_w


class ToolPolicy:
    """!
    @brief Prepare one effective configuration for checks and repairs.
    @details Repository rules extend the baseline. Unsupported settings fail
    rather than silently replacing shared rules. Native tools validate option
    values such as rule codes and Python versions.
    """

    # These options describe the project without disabling checks.
    PROJECT_OPTIONS = {
        "ruff.target-version",
        "ruff.src",
        "mypy.python_version",
        "mypy.mypy_path",
        "mypy.cache_dir",
    }
    # List additions are combined with the corresponding baseline list.
    LIST_OPTIONS = {
        "ruff.lint.select",
        "ruff.lint.extend-select",
        "ruff.lint.isort.known-first-party",
        "ruff.lint.isort.known-third-party",
        "ruff.lint.flake8-bugbear.extend-immutable-calls",
        "mypy.enable_error_code",
    }
    # Optional mypy checks can only be enabled, never disabled.
    STRICT_OPTIONS = {
        "disallow_any_generics",
        "disallow_untyped_calls",
        "disallow_untyped_decorators",
        "disallow_incomplete_defs",
        "disallow_subclassing_any",
        "strict_equality",
        "strict",
        "strict_bytes",
        "extra_checks",
        "warn_return_any",
        "warn_unreachable",
    }

    def __init__(self, root: Path) -> None:
        """!
        @brief Load the shared baseline and this repository's additions.
        @param root Repository containing pyproject.toml.
        @throws ValueError Configuration replaces baseline checks or uses
        unsupported options. The error names the rejected setting.
        """
        self.root = root.resolve()
        self.baseline = Path(__file__).with_name("baseline.toml")
        self.settings = tomllib.loads(self.baseline.read_text())["tool"]
        self.check_config_files()
        manifest = self.root / "pyproject.toml"
        tools = tomllib.loads(manifest.read_text()).get("tool", {})
        self.additions = {
            name: tools[name] for name in ("ruff", "mypy") if name in tools
        }
        for name, settings in self.additions.items():
            self.merge(self.settings[name], settings, name)
        self.directory = self.root / "artifacts/quality"

    def check_config_files(self) -> None:
        """!
        @brief Reject separate root configs that would otherwise be ignored.
        @throws ValueError A standalone Ruff or mypy configuration is present.
        """
        for name in ("ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini"):
            if (self.root / name).exists():
                raise ValueError(
                    f"Move {name} settings into pyproject.toml for SILTQ"
                )

    def merge(
        self, target: dict[str, Any], additions: Any, section: str
    ) -> None:
        """!
        @brief Add supported settings without replacing shared requirements.
        @param target Baseline table updated with the accepted additions.
        @param additions Consumer table read from pyproject.toml.
        @param section Dotted section name used to identify options and errors.
        @throws ValueError The table or one of its options is unsupported.
        """
        if not isinstance(additions, dict):
            raise ValueError(f"tool.{section} must be a table")
        for key, value in additions.items():
            option = f"{section}.{key}"
            if isinstance(target.get(key), dict):
                self.merge(target[key], value, option)
            else:
                target[key] = self.option(option, value, target.get(key))

    def option(self, name: str, value: Any, baseline: Any) -> Any:
        """!
        @brief Validate a repository option against its baseline value.
        @param name Dotted tool option being added.
        @param value Repository value to validate.
        @param baseline Shared value, or None for an additional option.
        @return Accepted value, including baseline entries for list options.
        @throws ValueError The setting could weaken checks or is unsupported.
        """
        if name in self.LIST_OPTIONS:
            return self.merge_list(name, value, baseline or [])
        if name in self.PROJECT_OPTIONS:
            return value
        if name == "mypy.overrides":
            return self.overrides(value)
        if self.accepts(name, value, baseline):
            return value
        raise ValueError(
            f"tool.{name} is not an additive setting. "
            "Keep the shared baseline and use documented inline exceptions "
            "or tools/exclusions.py where needed."
        )

    @staticmethod
    def merge_list(name: str, value: Any, baseline: list[str]) -> list[str]:
        """!
        @brief Preserve baseline list entries when adding repository entries.
        @param name Dotted setting name used in errors.
        @param value Repository list to validate and append.
        @param baseline Shared entries that must remain present.
        @return Combined list without duplicate entries.
        @throws ValueError The repository value is not a list of strings.
        """
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"tool.{name} must be a list of strings")
        return list(dict.fromkeys([*baseline, *value]))

    def accepts(self, name: str, value: Any, baseline: Any) -> bool:
        """!
        @brief Recognize unchanged settings and supported stricter values.
        @param name Dotted tool setting under consideration.
        @param value Repository value to compare with the shared setting.
        @param baseline Shared value, or None for an additional setting.
        @return True when the setting preserves or strengthens the baseline.
        """
        if name == "ruff.line-length" and type(value) is int:
            return bool(1 <= value <= baseline)
        if name.startswith("ruff.lint.flake8-tidy-imports.banned-api."):
            if baseline is None:
                return True
        if name.removeprefix("mypy.") in self.STRICT_OPTIONS:
            return value is True
        return (
            baseline is not None
            and type(value) is type(baseline)
            and value == baseline
        )

    def overrides(self, entries: Any) -> list[dict[str, Any]]:
        """!
        @brief Validate module-specific mypy additions and missing-stub waivers.
        @param entries Native mypy override tables supplied by the repository.
        @return Validated tables. Missing-import waivers require named modules.
        @throws ValueError An override disables checks or waives every module.
        """
        if not isinstance(entries, list):
            raise ValueError("tool.mypy.overrides must be a list of tables")
        for entry in entries:
            modules = self.override_modules(entry)
            for name, value in entry.items():
                if name == "module":
                    continue
                if name == "ignore_missing_imports":
                    if value is True and all("*" not in m for m in modules):
                        continue
                    raise ValueError(
                        "Missing-import waivers need exact modules"
                    )
                self.option(
                    f"mypy.{name}", value, self.settings["mypy"].get(name)
                )
        return entries

    @staticmethod
    def override_modules(entry: Any) -> list[str]:
        """!
        @brief Read the module names targeted by a mypy override.
        @param entry Repository override table containing a module setting.
        @return Module names as a nonempty list.
        @throws ValueError The override has no usable module names.
        """
        if not isinstance(entry, dict) or not entry.get("module"):
            raise ValueError("Each mypy override must name its modules")
        modules = entry["module"]
        modules = [modules] if isinstance(modules, str) else modules
        if not isinstance(modules, list) or not all(
            isinstance(module, str) and module for module in modules
        ):
            raise ValueError("Override modules must be nonempty names")
        return modules

    def write(self) -> None:
        """!
        @brief Save the exact configuration passed to Ruff and mypy.
        @details Generated files live under artifacts/quality. Explicit config
        arguments prevent nested or user-level configs from replacing them.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "ruff.toml").write_text(
            tomli_w.dumps(self.settings["ruff"]), encoding="utf-8"
        )
        (self.directory / "mypy.toml").write_text(
            tomli_w.dumps({"tool": {"mypy": self.settings["mypy"]}}),
            encoding="utf-8",
        )

    def arguments(self, tool: str) -> list[str]:
        """!
        @brief Select the generated configuration for a tool command.
        @param tool Ruff or mypy command name in lowercase.
        @return Explicit config-file arguments for that tool.
        """
        self.write()
        flag = "--config" if tool == "ruff" else "--config-file"
        return [flag, str(self.directory / f"{tool}.toml")]
