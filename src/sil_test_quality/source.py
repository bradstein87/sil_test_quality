"""!
@brief File selection and source structure checks for the repo.
"""

import ast
import hashlib
import io
import os
import re
import runpy
import tokenize
from collections.abc import Iterator
from pathlib import Path

from . import configuration as policy


class ProjectSource:
    """!
    @brief Provide the repo files and exclusions used by checks.
    @details File lists reflect the current working tree. Generated content is
    skipped. Fingerprints include legacy files even when source checks exclude
    them.
    """

    GENERATED = {
        ".git",
        ".precommit",
        ".pre-commit",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "__pycache__",
        "build",
        "dist",
        "artifacts",
        ".web",
        ".states",
        ".python",
        ".bootstrap",
        ".reflex",
        "reflex.lock",
    }

    def __init__(self, root: Path) -> None:
        """!
        @brief Set the repo location and load legacy exclusions.
        @param root Repo directory to search for files and tools/exclusions.py.
        """

        self.root = root
        self.exclusions = self.read_exclusions()

    def read_exclusions(self) -> list[str]:
        """!
        @brief Read the legacy files excluded from source checks.
        @details Loads the repo-owned tools/exclusions.py. Entries must name
        individual files inside the repo, not directory patterns.
        @return Relative filenames from EXCLUDED_FILES. Empty when no exclusions
        file exists.
        @throws ValueError EXCLUDED_FILES is malformed or contains an
        unsupported path.
        """

        path = self.root / "tools/exclusions.py"
        if not path.is_file():
            return []
        entries = runpy.run_path(str(path)).get("EXCLUDED_FILES")
        if not isinstance(entries, (list, tuple)):
            raise ValueError(f"{path}: EXCLUDED_FILES must be a list or tuple")
        for name in entries:
            if not isinstance(name, str) or not name:
                raise ValueError(f"{path}: exclusions must name files")
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or any(character in name for character in "\\:*?[]")
                or (self.root / relative).is_dir()
            ):
                raise ValueError(
                    f"{path}: use specific repository files: {name}"
                )
        return [Path(name).as_posix() for name in entries]

    def directories(self) -> Iterator[tuple[Path, list[str]]]:
        """!
        @brief Walk the repo while skipping generated directories.
        @details Virtual-environment directories are yielded so callers can
        identify them by pyvenv.cfg, but their contents are not traversed.
        @return Directory paths paired with their immediate filenames for file
        discovery.
        """

        for directory, children, names in os.walk(self.root):
            children[:] = [
                name
                for name in children
                if name not in self.GENERATED
                and not name.endswith(".egg-info")
                and not (Path(directory) / name).is_symlink()
            ]
            if "pyvenv.cfg" in names:
                children.clear()
            yield Path(directory), names

    def files(self, *, include_excluded: bool = False) -> list[Path]:
        """!
        @brief List the repo files available for checks.
        @param include_excluded True to include legacy files for fingerprinting.
        Ordinary checks leave this false.
        @return Sorted file paths with generated content and symlinks omitted.
        """

        files = []
        for directory, names in self.directories():
            if "pyvenv.cfg" in names:
                continue
            for name in names:
                path = directory / name
                relative = path.relative_to(self.root).as_posix()
                if not path.is_symlink() and (
                    include_excluded or relative not in self.exclusions
                ):
                    files.append(path)
        return sorted(files)

    def fingerprint(self) -> str:
        """!
        @brief Calculate a fingerprint of the repo inputs.
        @details Includes filenames and contents, even for legacy exclusions.
        Generated artifacts and caches are left out.
        @return SHA-256 text used by QualityReport to detect renamed or changed
        files.
        """
        digest = hashlib.sha256()
        for path in self.files(include_excluded=True):
            relative = path.relative_to(self.root)
            content = path.read_bytes()
            digest.update(relative.as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(content).digest())
        return digest.hexdigest()

    def sizes(self) -> dict[str, int]:
        """!
        @brief Measure text file lengths.
        @return Relative filenames and physical line counts. Generated and
        binary files are omitted.
        """

        sizes = {}
        for path in self.files():
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "\0" not in content:
                relative = path.relative_to(self.root).as_posix()
                sizes[relative] = len(content.splitlines())
        return sizes

    def line_widths(self) -> tuple[list[str], dict[str, int]]:
        """!
        @brief Find Python lines that exceed the column limit.
        @details Counts indentation, comments and docstrings. Tabs advance to
        four-column stops. URLs, long names and noqa comments get no exception.
        Generated content and declared legacy exclusions remain outside scope.
        @return Findings followed by each readable file's maximum width.
        Findings put read errors first, then overlong lines, widest first.
        """
        findings = []
        errors = []
        widths = {}
        for path in self.files():
            if path.suffix not in {".py", ".pyi", ".pyw"}:
                continue
            relative = path.relative_to(self.root).as_posix()
            try:
                maximum = 0
                with tokenize.open(path) as stream:
                    for number, line in enumerate(stream, 1):
                        width = len(line.rstrip("\r\n").expandtabs(4))
                        maximum = max(maximum, width)
                        if width > policy.MAX_LINE_COLUMNS:
                            findings.append(
                                (
                                    width,
                                    f"{relative}:{number}: {width} columns "
                                    f"(limit is {policy.MAX_LINE_COLUMNS})",
                                )
                            )
                widths[relative] = maximum
            except (OSError, SyntaxError, UnicodeError) as error:
                errors.append(f"{relative}:1: cannot measure lines: {error}")
        findings.sort(key=lambda finding: finding[0], reverse=True)
        return errors + [message for _, message in findings], widths

    def inspect(self) -> tuple[list[str], list[str]]:
        """!
        @brief Check source structure and find inline exceptions.
        @return Two lists: blocking structure/comment issues, then inline
        exceptions to include in the report.
        """
        problems, suppressions = [], []
        for path in self.files():
            if path.suffix != ".py":
                continue
            relative = path.relative_to(self.root)
            try:
                content = path.read_text(encoding="utf-8")
                tree = ast.parse(content)
                problems.extend(self._test_classes(relative, tree))
                comments = tokenize.generate_tokens(
                    io.StringIO(content).readline
                )
                for token in comments:
                    if token.type != tokenize.COMMENT:
                        continue
                    location = f"{relative}:{token.start[0]}"
                    if re.search(r"\b(TODO|FIXME)\b", token.string, re.I):
                        problems.append(f"{location}: unfinished work comment")
                    if re.search(
                        r"noqa|type:\s*ignore|mypy:"
                        r"|pragma:\s*no (cover|branch)",
                        token.string,
                        re.I,
                    ):
                        suppressions.append(f"{location}: {token.string}")
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and len(node.bases) > 1:
                        problems.append(
                            f"{relative}:{node.lineno}: multiple inheritance"
                        )
            except (SyntaxError, UnicodeError, tokenize.TokenError) as error:
                problems.append(f"{relative}: cannot inspect: {error}")
        return problems, suppressions

    def _test_classes(self, path: Path, tree: ast.Module) -> list[str]:
        """!
        @brief Find test functions declared outside classes.
        @param path Relative filename used to identify test modules and locate
        issues.
        @param tree Python structure parsed from the file, containing its
        definitions.
        @return Structure messages for top-level test functions. Empty when none
        violate the rule.
        """
        if path.parts[0] != "tests" or not (
            path.name.startswith("test_") or path.stem.endswith("_test")
        ):
            return []
        problems = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            decorators = {
                ast.unparse(item.func if isinstance(item, ast.Call) else item)
                for item in node.decorator_list
            }
            if decorators & {"pytest.fixture", "fixture"}:
                continue
            problems.append(
                f"{path}:{node.lineno}: put {node.name} in a Test class"
            )
        return problems
